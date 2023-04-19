#!/usr/bin/env python3


# encoding: utf-8
#
# wmlxgettext -- generate a blank .pot file for official campaigns translations
#                    (build tool for wesnoth core)
#
#
# By Nobun, october 2015
# Thanks to Elvish Hunter for writing code for coloring text under windows
#
#                              PURPOSE
#
# wmlxgettext is a python3 tool that replace the old (but very good)
# perl script with the same name.
# Replacing perl with python3 will ensure more portability.
#
# wmlxgettext is a tool that is directly used during wesnoth build process
# to generate the pot files for the core campaigns.
#
#                              USAGE
#
# If you want to learn how to use wmlxgettext, read the online End-User
# documentation at:
# http://wmlxgettext-unoff.readthedocs.org/en/latest/enduser/index.html
#
#                   SOURCE CODE DOCUMENTATION
#
# While the source code contains some comments that explain what it does at
# that point, the source code is mainly explained on source documentation at:
# http://wmlxgettext-unoff.readthedocs.org/en/latest/srcdoc/index.html

import argparse
from copy import copy
from datetime import datetime
import os
import signal
import sys
import warnings
import pywmlx
from wesnoth.wmltools3 import CrossRef
from wesnoth.wmlmacro import AST, Macro, CrossRefHelper, ReferenceHelper, GlobalWMLMacros

from pprint import PrettyPrinter
pp = PrettyPrinter(indent=4)

def on_macro(node):
    print("Macro parsed")
    print(node)

def main():
    AST.parse(r'Hello, very {ON_DIFFICULTY4 (" test prevOpt whitespace") ("test nextOpt whitespace ") ("test noneOpt whitespace") (" test bothOpt whitespace ")} world .', on_macro)

if __name__ == "__main__":
    main()
