#!/bin/sh
set -eu
"$PREFIX/bin/python" -I -B "$PREFIX/manager/post_install.py" "$PREFIX"
