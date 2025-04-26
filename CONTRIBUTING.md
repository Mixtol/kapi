# Шаги для разработки проекта

## 1) Установка зависимостей
```
python -m venv .venv
.venv/Scripts/activate  # Windows
source .venv/bin/activate  # Linux
pip install -r requirements.dev.txt
```

## 2) Установка pre-commit хуков
```
pip install pre-commit  # Если не установлен
pre-commit install
```

## 3) При использовании PyCharm установите формат докстрингов "Google"
Настройки -> Tools -> Docstrings -> Docstring format -> "Google"

## 4) Правила оформления коммитов

Допускается 10 типов коммитов:

|   ТИП    |                         Описание                          |
|:--------:|:--------------------------------------------------------:|
|   fix    |                   Исправление ошибки                     |
|  hotfix  |          Срочное исправление критических ошибок          |
|   feat   |               Добавление нового функционала              |
|  style   |     Правки стиля кода (без изменения функционала)        |
| refactor |     Изменения кода без исправления ошибок или добавления функционала |
|   perf   |            Изменения для повышения производительности    |
|  build   |     Сборка проекта или изменение внешних зависимостей    |
|    ci    |            Настройка CI                                  |
|   docs   |                    Обновление документации               |
|  revert  |                 Откат к предыдущим коммитам              |
|   test   |                     Добавление\изменение тестов                    |

Шаблон мерджа или коммита:
ТИП(ID карточки): Что произойдет после мерджа коммита

Пример:
feat(ISSUE-8922): Добавлен класс для загрузки данных в MISP

То есть после мерджа этот коммит добавит класс для выгрузки данных в MISP.

## 5) Закоммитьте изменения и запушите в непродуктивную ветку

Все pre-commit хуки применяются автоматически к файлам в коммите.
Для ручной проверки перед коммитом выполните:
```
pre-commit run --all-files
```

---

# Steps for project development (Zabugor Edition)

## 1) Install dependencies
```
python -m venv .vevn
.venv/scripts/activate # Windows
source/bin/activate # Linux
pip install -r requirements.txt
```

## 2) Install pre-commit hooks
```
pip install pre-commit # If not
pre-commit install
```

## 3) If PyCharm is used, then set the docstring format type to "Google"
Settings -> Tools -> Docstrings -> Docstring format -> "Google"

## 4) Read the rules for making commits

Commits can be of 10 types:

|   Type   |                         Description                          |
|:--------:|:------------------------------------------------------------:|
|   fix    |                           Bug fix                            |
|  hotfix  |                  Quick fix of critical bugs                  |
|   feat   |                  	Adding new functionality                   |
|  style   |    	Code style edits (tabs, indents, dots, commas, etc.)     |
| refactor | 	Code edits without correcting errors or adding new features |
|   perf   |           	Changes aimed at improving performance            |
|  build   |    	Building a project or changing external dependencies     |
|    ci    |           	Configuring CI and working           |
|   docs   |                   	Updating documentation                    |
|  revert  |                	Rollback to previous commits                 |
|   test   |                         Adding tests                         |

The commit is created according to the following template:
TYPE(Card ID in Jira): What will happen after the commit merge

Example:
feat(EXTSOC-8922): Add class to load data into MISP

That is, after the merge, this commit will add a class for uploading data to MISP.

# 5) Commit your changes and push it to non productive branch

All pre-commit hooks will used automaticly for commited files.
If you wan to check it manualy first then run `pre-commit run --all-files`
