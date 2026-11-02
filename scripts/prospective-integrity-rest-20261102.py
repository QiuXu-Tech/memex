#!/usr/bin/env python3
"""Run the six remaining registered tasks with the published concurrency amendment."""
import importlib.util
import pathlib

path = pathlib.Path(__file__).with_name('prospective-integrity-20261102.py')
spec = importlib.util.spec_from_file_location('integrity_study', path)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
study.agent.CONCURRENCY = 2
study.run_phase('rest')
