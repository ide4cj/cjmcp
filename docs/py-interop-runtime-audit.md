# Runtime-аудит py_interop для issue #6

Срез: 2026-10-28. **Кандидат `ded6e681bea82f85d0b8ceb2025d0b38e52ad14d`
отклонён для долгоживущего Cangjie ↔ Python моста.** Исполнение подтверждает
поддержку ряда значений, но принудительный Cangjie GC завершает процесс SIGSEGV
при освобождении Python-ссылок. Есть независимые дефекты удержания callbacks,
registry, перевода исключений и повторной инициализации интерпретатора.

Пригодная ревизия не выбрана: результаты не дают оснований закреплять кандидата.
`cjpm.lock` оставлен без изменений; старый `c66c1825…` в нём **не считается
прошедшей runtime-проверку альтернативой**. Обновление зависимости отложено до
появления ревизии с исправлениями и повторного выполнения этих проб. Это
отрицательный результат выбора, а не рекомендация старой версии. Более новые
`431a05e`/`ee670bc` не испытывались и не рекомендуются этим отчётом.

## Границы и воспроизведение

Внешний Cangjie-код владеет базой анализа, проектом и кешами. Python получает
контекст на один скрипт. Проба `Owner` моделирует такого внешнего владельца:
сто запросов получают новые словари, счётчик владельца сохраняется. Здесь нет
реальной `AnalysisDatabase`, MCP-сервера или оценки производительности. Python
зависимости в loupe/cjls не добавлены; исходники loupe4py не менялись.

[Host](../tools/interop/runtime.cj) и [runner](../tools/interop/probe.py) содержат
18 compile-проб и 47 runtime-проб. Каждая runtime-проба — отдельный процесс с
таймаутом 20 секунд и отключённым core dump. Runner сохраняет команды, исходники,
макроразвёртки, stdout/stderr, exit codes, версии, SHA-256 libpython и diff
исходников interop. Ожидания находятся в [expected.json](../tools/interop/expected.json).
Ненулевой exit **отдельного дочернего процесса** может быть ожидаемым результатом
аудита; exit 0 **runner** означает совпадение всех наблюдений с ожиданиями, а не
готовность библиотеки к эксплуатации. `--record-only` собирает новые наблюдения
без проверки baseline; это не проверка успешности runtime-проб.

Проверенные окружения:

| Компонент | Значение |
|---|---|
| Cangjie | `1.3.0-alpha.20261014001050`, cjnative, `x86_64-unknown-linux-gnu` |
| ОС | Linux `7.2.9-arch1-1`, x86_64, glibc `2.44` |
| CPython A | `3.14.8`, GCC `16.2.1 20260810`, системная `/usr/lib/libpython3.14.so.1.0` |
| CPython B | `3.12.11`, python-build-standalone, Clang `20.1.4`, отдельный libpython и stdlib |
| Python ABI | Обычные GIL builds, `Py_DEBUG=0`, `Py_GIL_DISABLED=0` либо не определено |
| py_interop | `ded6e681bea82f85d0b8ceb2025d0b38e52ad14d`, собственных зависимостей нет |
| Сборка interop | `python build/build.py build`, release `-O2`, dynamic; свежий target |
| Сборка host и compile-проб | `cjc`, стандартный `-O0`, без LTO, `-Woff all` |
| Остальные зависимости cjmcp | loupe/cjls `371069c9312b8ddb4cc5045349937235218693f8`; не участвуют в пробах |

Полные результаты: [3.14.8](interop-evidence/cpython-3.14.8.json),
[3.12.11](interop-evidence/cpython-3.12.11.json),
[диагностическая правка / 3.14.8](interop-evidence/diagnostic-gil-cpython-3.14.8.json).
В JSON сохранены фактические пути этой машины; в командах ниже замените SDK и
пути CPython на свои. Драйвер Python, его headers, libpython и stdlib должны
относиться к одной установке.

```sh
# Запускать из корня cjmcp, с выбранным SDK в PATH.
git clone https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop.git /tmp/interop-audit
git -C /tmp/interop-audit checkout --detach ded6e681bea82f85d0b8ceb2025d0b38e52ad14d
(cd /tmp/interop-audit && PYTHON_INCLUDE_PATH=/usr/include/python3.14 python3 build/build.py build)
python3 tools/interop/probe.py \
  --interop /tmp/interop-audit \
  --sdk /home/filaco/.cjpm/toolchains/nightly-2026-10-14 \
  --libpython /usr/lib/libpython3.14.so \
  --out /tmp/interop-evidence-new
```

`--out` должен отсутствовать перед запуском. Для CPython 3.12 использованы
`uv python install 3.12 --install-dir /tmp/cjmcp-issue6-python` и отдельный checkout
interop, собранный его `bin/python3.12` с `PYTHON_INCLUDE_PATH`, указывающим на его
`include/python3.12`. При запуске runner этим Python обязательно задать
`PYTHONHOME=/tmp/cjmcp-issue6-python/cpython-3.12.11-linux-x86_64-gnu` и передать
его `lib/libpython3.12.so`. Без PYTHONHOME переносимая сборка пыталась найти stdlib
в `/install` и прекращала инициализацию с `ModuleNotFoundError: encodings`;
это ошибка конфигурации, не результат проверки конвертаций.

## ABI, регистрация и исполнение

Оба libpython загружаются явно через `Python.load(path)`, сообщают ожидаемую
версию и выполняют Python с вызовами Cangjie API. Использован штатный генератор
констант из **соответствующих headers**, а не только `cjpm build` с готовым файлом:
`Py_TPFLAGS_DEFAULT` меняется с поставляемого `0x40000` на `0x0` в обоих окружениях.
Размеры `PyObject`, `PyMethodDef`, `PyGetSetDef`, `PyType_Spec`, `PyType_Slot`
равны соответственно 16, 32, 40, 32, 16 байтам. Generated constants и diff
сохранены в evidence; это ожидаемая платформенная генерация, не исправление
логики interop. Совместимость других платформ, debug/free-threaded CPython,
версий Python и компиляторов не установлена.

Классы регистрируются вручную через `T.pyClass()`, функции — через
`PythonTopLevelFunctions`, затем передаются в `PyDict`. Проверены конструктор,
метод, getter, setter класса, перегрузки, расширение типа в том же пакете,
`@PyIgnore` и наследование. `Derived.pyClass()` неоднозначен; явный
`marker: PyInteropTypeMarker<Derived>()` устраняет compile-ошибку. Эта регистрация
в scope не создаёт импортируемый CPython extension или отдельный модуль.

`Python.exec(code, locals: scope)` использует globals из `__main__`. Верхнеуровневый
доступ к `owner` работает, но определённая скриптом функция получает `NameError`
при доступе к нему. Минимальный проверенный адаптер — Python builtin
`exec(code, scope, scope)`, вызываемый из Cangjie (`scope_function_adapter`).
Для requests нужен один новый общий globals/locals-словарь, содержащий нужные
bindings; база и кеши остаются у внешнего владельца. Межзапросная изоляция
модулей, builtins, IO и процессов этим не обеспечивается.

## Значения и ошибки: фактические результаты

`↔` ниже означает Python → Cangjie → Python через реальный вызов. Результаты
совпадают на двух CPython, кроме отдельно указанных различий shutdown.

| Пробы | Направление и факт | Ограничение / минимальный обход |
|---|---|---|
| `unicode` | String ↔: кириллица и emoji сохраняются | Проверен UTF-8, не произвольные байты |
| `nul_string` | String ↔ с `a\0b`: AssertionError, значение не сохраняется | Использовать length-aware C API; до исправления отклонять NUL. По этой пробе нельзя разделить потери на входе и выходе |
| `record`, `extension` | Entry ↔: Int64/String поля, результат после вызова и метод расширения работают | Immutable DTO; это преобразование через registry, не гарантия identity |
| `array_string`, `array_record` | Array<String>/Array<Entry> ↔ работают | Копирование контейнера, lifecycle элементов см. ниже |
| `option` | ?String ↔: None и Some(String) работают | Отсутствие значения не означает отсутствие аргумента |
| `nested` | ?Array<Entry> ↔: None и вложенные объекты работают | Не доказывает произвольную рекурсивную композицию всех контейнеров |
| `pair` | (Int64,String) ↔ работает | Не обобщать на tuple любой арности |
| `array_pair_in` | Python → CJ Array<(Int64,String)> читается, возвращается размер 2 | Обратное направление не компилируется; выводить Array<Entry> |
| `triple_out` | CJ → Python (Int64,String,Bool) работает | Вход проверять отдельно |
| `triple_in` | Python → CJ корректная тройка даёт SystemError: NULL without exception | Reader ошибочно требует размер 2; пока именованный DTO |
| `triple_short` | Python → CJ пара вместо тройки: SystemError: result with exception set | Reader пытается читать третий элемент; нужна проверка размера 3 до чтения |
| `callback` | Python callable → CJ → Python: аргумент 7, возвращённая строка "7" сохраняются | Только синхронный успешный вызов |
| `callback_retention` | После `owner.save(f)` и `del f; gc.collect()` Python weakref пуст | CJ-замыкание держит сырой указатель. До исправления callable обязан оставаться у Python-владельца; сохранённое CJ-замыкание этого не делает |
| `callback_error`, `callback_wrong_return`, `callback_noncallable` | Python → CJ callback: ZeroDivisionError, неверный return и non-callable приводят к NoneValueException в host | Проверять callable/return, сохранять Python exception и переводить его на границе; текущего reader недостаточно |
| `wrong_string`, `missing_arg`, `extra_arg`, `wrong_record`, `wrong_array` | Python → CJ: неверные значения/арность дают SystemError, NULL without exception | Валидация в facade помогает входам; общий trampoline должен ставить TypeError |
| `invalid_ctor` | Неверный тип поля конструктора корректно даёт Python TypeError | Это не свойство всех сгенерированных callbacks |
| `class_mutation`, `invalid_setter` | Валидный setter класса изменяет внешний объект; неверный тип молча сохраняет старое значение | В facade валидировать до присваивания; общий setter должен отвергать неверный тип |
| `forged_identity` | Посторонний Python-класс с `__cangjie_identity__` даёт NoneValueException в host | Marker не заменяет проверку Python-типа/storage; исходник читает чужую память. Наблюдение не гарантирует безопасный отказ для других объектов |
| `default_explicit`, `default_omitted` | Явный keyword работает; пропуск default даёт SystemError | Python wrapper подставляет default явно |
| `cj_exception` | CJ → Python: Exception("cj-boom") выходит в Cangjie host как ExclusiveScopeException | Общего перевода в Python RuntimeError нет; нельзя выпускать исключения через C ABI |
| `python_exception` | Python → CJ: ValueError("py-boom") доходит как PythonException внутри ExclusiveScopeException; следующий скрипт выполняется | При обработке учитывать `causedBy`/`toString()`, не только `.message`; тип и traceback представлены текстом |

Фактический выход процесса при ошибках — 1, при успешных assertions — 0.
Для callbacks исключение проходит через C ABI: даже если на этой машине host
его перехватил, это не подтверждённый безопасный механизм перевода ошибок.

## GIL и владение

`threads_gil` выполняет Python и вызов echo из четырёх Cangjie задач под
`withGIL`; все задачи завершаются. `without_outer_gil` подтверждает успешный
простой вызов `Python.exec` с его внутренним захватом GIL. `withGIL` использует
`exclusiveScope`, поэтому исключения оборачиваются в `ExclusiveScopeException`.
Эти проверки не доказывают корректность произвольной миграции задач, shutdown
с активными задачами или параллельных изменений внешней базы.

| Проба | Неизменённая логика ded6e681 | Что это устанавливает |
|---|---|---|
| `result_lifetime` | Entry доступен после возврата из метода и Python `gc.collect()` | Только Python GC; не Cangjie GC |
| `fresh_scope` | 100 новых scopes, `previous_request` не переносится, внешний `owner.calls == 100` | Состояние живёт у владельца; это функциональная проверка, не измерение утечек/скорости |
| `reference_native` | `getIncPtr()` увеличивает refcount списка на 1; явный `Py_DecRef` под GIL возвращает прежний refcount | Освобождена одна native-ссылка. Сам список остаётся живым у других владельцев |
| `reference_gc` | SIGSEGV на обоих Python, стек `gc-helper → Reference.~init → Py_DecRef/_Py_Dealloc` | Финализатор выполняет decref без GIL |
| `result_after_request` | Возврат PyObj из функции с локальным scope, затем CJ GC: SIGSEGV на обоих Python | Успешный return недостаточен для гарантии времени жизни |
| `registry_release` | При попытке дождаться GC — тот же SIGSEGV | До устранения финализатора нельзя делать вывод об освобождении registry по этому запуску |
| `unload` | Один unload с живыми wrappers, последующий GC: exit 0 | Проверен только последовательный shutdown без активных задач; финализаторы пропускают decref после `envInit=false` |
| `reload` | 3.14: AttributeError у Owner после повторной загрузки; 3.12: SIGSEGV | Повторная инициализация не поддерживается проверенным путём; кешированные типы переживают интерпретатор |

Для отделения registry от аварии финализатора добавлена
[диагностическая правка](../tools/interop/diagnostic-finalizer.patch): захват
`PyGILState_Ensure/Release` вокруг `Py_DecRef` в `Reference.~init`.
Это **не выбранная ревизия и не готовое исправление**: гонка с unload,
интерпретаторы, уничтожение кешированных типов и ownership других C API остаются
непроверенными. Её результаты нельзя приписывать исходной ревизии.

После этой правки на 3.14:

1. `reference_gc` и `result_after_request` завершаются успешно.
2. Контрольный CJ Owner без proxy освобождается после bounded GC polling.
3. После `del tracked`, Python GC и до 20 CJ GC с ожиданием 10 ms weakref на CJ
   Owner остаётся живым: `REGISTRY_FREED false`.
4. После отдельного `PyProxy.del(id)` weakref очищается:
   `AFTER_REGISTRY_DELETE true`. `ctx` остаётся живым до конца проверки, сам
   отслеживаемый объект создаётся в отдельной функции без локального strong root.

Это подтверждает удержание registry отдельно от задержки GC. В исходниках
[PyNativeDescriptor][descriptor] нет dealloc-слота удаления registry;
[PyProxy][proxy] хранит сильные ссылки. Ручное удаление id в пробе — диагностический
шаг: вызывать методы proxy после него нельзя. Оно не является безопасным
общим `close()` для фасада. Нужен interop cleanup, связанный с Python-владением,
либо собственный проверенный opaque handle registry с явной инвалидизацией.

Воспроизведение диагностики в отдельном checkout, **не поверх baseline evidence**:

```sh
git clone /tmp/interop-audit /tmp/interop-diagnostic
git -C /tmp/interop-diagnostic apply "$PWD/tools/interop/diagnostic-finalizer.patch"
(cd /tmp/interop-diagnostic && PYTHON_INCLUDE_PATH=/usr/include/python3.14 python3 build/build.py build)
python3 tools/interop/probe.py \
  --interop /tmp/interop-diagnostic \
  --sdk /home/filaco/.cjpm/toolchains/nightly-2026-10-14 \
  --libpython /usr/lib/libpython3.14.so \
  --expected tools/interop/expected-diagnostic.json \
  --out /tmp/interop-diagnostic-evidence-new
```

## Перепроверка G0–G10

[Исторический аудит][historical] описывал c66c1825; его выводы не следует
переносить на кандидата без поправок.

| Ограничение | Статус ded6e681 и уровень доказательства | Адаптер / общая работа interop |
|---|---|---|
| G0: доступность сгенерированного API | Исправлено upstream в beb7aa0. String/struct/callback реально выполняются из отдельного host package | Форк для G0 не нужен |
| G1: чужие объявления и extend | Runtime расширения уже bound Entry в том же пакете работает. `unbound_extend` и `bound_cross_extend` не компилируются: descriptor не найден. `external_interface` запрещён языком; `external_converter` компилируется | Concrete wrappers / overload-конвертер. Последний compile-only: не доказывает Python-класс Value или вложенные контейнеры |
| G2: defaults | `default_omitted` runtime SystemError | Wrapper подставляет значение; общий parser должен учитывать optional args |
| G3: enum | `enum_result` не компилируется из-за порядка литералов; `enum_payload` падает при macro expansion. В кандидате уже есть IntoPy/FromPy: историческое утверждение об их отсутствии устарело | Пока tags/DTO. Исправить генерацию, затем проверить roundtrip вариантов в исполнении; runtime enum не подтверждён |
| G4: tuples/композиция | Пары ↔, тройки CJ → Python работают; вход тройки сломан; Array<pair> обратно не компилируется | Именованные DTO; исправление reader3 и общих конвертеров |
| G5: callbacks | Синхронный Python callback работает; retention/ошибки сломаны. `callback_out` не компилируется | Хранить callable у Python-владельца в пределах запроса; общий reader должен владеть ссылкой и переводить ошибки. Возврат CJ callable требует ручной регистрации и отдельной проверки ownership |
| G6: generics | `generic` не компилируется; `concrete_generic` компилируется | Конкретный forwarding API; произвольная monomorphization не реализована |
| G7: конструкторы/изменяемость | `private_ctor` и `mutable_struct` не компилируются; class mutation работает, invalid setter молчит | Immutable DTO, factories и валидация. Общие output-only bindings и write-back struct требуют исправлений |
| G8: отбор/наследование | `ignored_field` компилируется; selection, overloads и inheritance выполняются. Для derived pyClass нужен explicit marker | `@PyIgnore` и базовые inherited методы уже поддержаны. Политика static/instance mixed overloads, static fields, aliases и произвольной macro composition этим набором не установлена; явно выбранные wrapper-методы |
| G9: ошибки и storage | Неверные функции дают SystemError; forged identity и CJ/callback exceptions выходят в host | До любого чтения storage проверять реальный тип. Нужен общий exception trampoline; одной Python-валидации недостаточно |
| G10: bootstrap | `registration`, fresh_scope и same_dict adapter исполняются | Внешний CJ host регистрирует API и управляет scope; автоматического CPython import/MCP transport нет |

Имена всех compile-проб с точными ожидаемыми ошибками перечислены в expected.json;
логи содержат исходный код и диагностики. Дополнительные ownership/GIL блокеры
расположены за пределами первоначальных compile-ограничений G0–G10.

## Решение для следующего шага

Для фасада достаточно concrete immutable DTO, явных defaults/валидации,
одного globals/locals scope и сохранения состояния у внешнего Cangjie владельца.
Это локальная адаптация; она не устраняет аварийные финализаторы библиотеки.

Перед выбором ревизии и изменением lock обязательны общие исправления interop:
GIL-safe освобождение с согласованным shutdown, balanced owned/borrowed refs,
удаление registry по времени жизни proxy, удержание callable, exception boundary
на каждом C callback, проверка типа до чтения storage. Для нужного контракта
также потребуются исправление triple reader и length-aware строки либо явный
запрет NUL. Повторная загрузка интерпретатора может быть запрещена контрактом
host; один процесс должен иметь один согласованный lifetime Python.

После появления точной upstream-ревизии повторить набор, обновить ожидания
**по новым фактическим результатам**, затем отдельно утвердить lock. Здесь
диагностическая правка намеренно не скрывает отсутствие пригодной ревизии.

[historical]: https://github.com/ide4cj/cjmcp/blob/b09dddbd8441ea106cf2cb67e1fbde0ab3228b2a/docs/python-api-map.md
[descriptor]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/ded6e681bea82f85d0b8ceb2025d0b38e52ad14d/src/py_native_descriptor.cj
[proxy]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/ded6e681bea82f85d0b8ceb2025d0b38e52ad14d/src/pyproxy.cj
