# Retained native parsers

Surfaces is retained in place as Tarav's built-in Python and Markdown parsing
foundation. Future workflows may use these native models for inline annotations
or other source-aware operations. Parsers expose syntax and source spans;
consuming workflows own annotation semantics.

The standalone `tarav surfaces` command is disconnected from runtime composition.
Its command adapter remains here for deliberate future reuse, with isolated
tests. It is not a currently exposed Tarav workflow.

The Markdown parser remains an active dependency of `tarav.stdlib.mdblocks`.
Do not remove it or confuse this retained parser foundation with the retired
Skillware annotation compiler. Python parser tests are also retained.
