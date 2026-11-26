#!/bin/bash
# drop the pyenv hashlib blake2 import noise from a run's output
grep -v "blake2\|^Traceback\|^  File \|\^\^\^\|raise ValueError\|globals()\[\|return __get\|^ERROR:root\|DeprecationWarning\|utcfromtimestamp"
