/**
 * Offline stub for `@deepseek-ai/dsh-tools`.
 *
 * `lib/tools.js` calls `defineTool(definition)` only to get a typed tool
 * definition back; the real function normalizes JSON schemas but does not
 * change the object shape the tests inspect. The tests register tools on a
 * fake context and call their `execute` functions directly.
 */

/**
 * Return the tool definition unchanged.
 * @template T
 * @param {T} definition - Tool definition.
 * @returns {T} The same definition.
 */
export function defineTool(definition) {
  return definition
}

/** Kept for compatibility with callers that validate tool schemas. */
export function assertObjectJsonSchema() {}

export default { defineTool, assertObjectJsonSchema }
