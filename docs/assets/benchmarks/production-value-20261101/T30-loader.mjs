import fs from 'node:fs'
import {fileURLToPath} from 'node:url'
import ts from '/checks/typescript/lib/typescript.js'
const root='file:///work/packages/happy-dom/src/'
export async function resolve(specifier, context, nextResolve) {
  if (context.parentURL?.startsWith(root) && (specifier.startsWith('./') || specifier.startsWith('../')) && specifier.endsWith('.js')) {
    const url=new URL(specifier.slice(0,-3)+'.ts',context.parentURL)
    if(fs.existsSync(fileURLToPath(url))) return {url:url.href,shortCircuit:true}
  }
  return nextResolve(specifier,context)
}
export async function load(url,context,nextLoad) {
  if(url.startsWith(root) && url.endsWith('.ts')) {
    const text=fs.readFileSync(fileURLToPath(url),'utf8')
    const output=ts.transpileModule(text,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022,experimentalDecorators:true,verbatimModuleSyntax:true},fileName:fileURLToPath(url)}).outputText
    return {format:'module',source:output,shortCircuit:true}
  }
  return nextLoad(url,context)
}
