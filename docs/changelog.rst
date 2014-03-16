Changelog
=========

Version 0.5.0
-------------

* Changed :obj:`aspectlib.debug.log`:

    * Renamed `arguments` to `call_args`.
    * Renamed `arguments_repr` to `call_args_repr`.
    * Added `call` option.
    * Fixed issue with logging from old-style methods (object name was a generic "instance").

* Fixed issues with weaving some types of builtin methods.
* Allow to apply multiple aspects at the same time.
* Validate string targets before weaving. ``aspectlib.weave('mod.invalid name', aspect)`` now gives a clear error
  (``invalid name`` is not a valid identifier)
* Various documentation improvements and examples.

Version 0.4.1
-------------

* Remove junk from 0.4.0's source distribution.

Version 0.4.0
-------------

* Changed :obj:`aspectlib.weave`:

    * Replaced `only_methods`, `skip_methods`, `skip_magicmethods` options with `methods`.
    * Renamed `on_init` option to `lazy`.
    * Added `aliases` option.
    * Replaced `skip_subclasses` option with `subclasses`.

* Fixed weaving methods from a string target.
