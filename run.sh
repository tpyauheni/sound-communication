#!/usr/bin/sh

PYTHON=python

proj_root="$(dirname $0)"
src_dir="$proj_root/src"
venv_dir="$proj_root/.venv"

[ x"$VIRTUAL_ENV" = x"" ] && source "$venv_dir/bin/activate"

"$PYTHON" "$src_dir/main.py" --disable-log "$@"

