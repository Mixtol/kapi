# Changelog
## Version 2.1.3 - 09/06/25
Core Updates:

1. Implemented data conversion between with 2 new methods:
  - Active List to Dictionary data structures
  - Dictionary to Active List data structures

2. Lazy Initialization
Modules now initialize on first access for performance

3. Renamed functions and typos:
  - fixed many typos like `dictionai` -> `dictionary`
  - All `_import` functions to `import_data`
  - activeLists function `list` now named `lists`

4. Added `@properties` for IDE support

## Version 2.1.4 - 10/06/25
- Removed init method for classes for KUMA components as initialization is being done in KumaRestAPIModule
- Changed imports from relative to absolute because it is considered best-practice
- Removed unused imports (from typing module)
- Translated annotations to ENG
- Changed logging.py to _logging.py because logging is reserved for module name
- Added datatypes annotations
- Added specific versions for modules in requirements.dev.txt
- Fixed to_dict unic validation
- Updated README.md
- Added TODO

## Version 2.1.5 - 17/06/25

Update for `.active_lists.to_dictionary` function:
- Fixed headers selection
- Optimized set for values
- Added *clear* dictionary option

## Version 2.1.6 - 18/06/25

Update for `.active_lists.to_dictionary` function:
- Fixed custom key


## Version 3.0.0 - 01/09/25

- Added new methods for *resources*
- Added new methods for *settings*
- Fix for *system/backups*: Now you can add you timeout value and changed POST -> GET for create bak method.
