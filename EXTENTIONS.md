# Расширенные функции KAPI

Этот файл описывает вспомогательные коплексные методы, 
упрощающие задачи операционного сопровождения KUMA.

---

## `dictionaries.to_active_list()`

```python
status, resp = client.dictionaries.to_active_list(
    dictionary_id="UUDD-1",  # ID словаря
    active_list_id="UUID-2",  # ID AL, куда импортируем
    correlator_id="UUDD-3",  # ID сервиса, к которому относится AL
    active_list_id="UUIDD-4",  # ID AL, куда импортируем
    dictionary_key="key",   # какое поле словаря станет ключом
    clear=True             # очистить AL перед импортом
)
if status == 200:
    print("Данные импортированы")
````

## `active_lists.to_dictionary()`
Если *active_list_key* и *dictionary_key* равны `key`, то аргументы не нужны.
```python
status, resp = client.active_lists.to_dictionary(
    correlator_id="UUID-1",
    active_list_id="UUID-2",
    dictionary_id="UUDD-3",
    active_list_key="SourceUserName", # какое поле AL станет ключом словаря
    dictionary_key="Name",      # Наименование ключевого столбца в словаре
    need_reload=1             # перезагрузить зависимые сервисы
)
if status == 204:
    print("Словарь обновлён")
```