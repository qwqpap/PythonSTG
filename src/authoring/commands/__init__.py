"""Domain authoring commands and the shared command stack.

Every author mutation flows through a :class:`~src.authoring.commands.base.Command`
on one document's :class:`~src.authoring.commands.base.CommandStack`.  Command
modules are Qt-free by contract; panels emit typed intents instead of importing
these directly.
"""
