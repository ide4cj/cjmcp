# Первый контракт анализа для Python

Контракт для [issue #7](https://github.com/ide4cj/cjmcp/issues/7): внешний
Cangjie-владелец передаёт скрипту `analysis` и `params`; Python вызывает hover,
diagnostics и definition, получая самостоятельные неизменяемые значения.
Сессия, база, кеши и macro server принадлежат внешнему модулю, в будущем MCP.
`Workspace.open/close` и постоянный REPL не нужны.

Это спецификация для реализации, а не уже работающий binding. Точные Python
объявления находятся в [initial-analysis-api.pyi](initial-analysis-api.pyi),
скрипт — в [examples/initial_analysis.py](../examples/initial_analysis.py).
Контракт не определяет MCP JSON schemas и не ограничивает более широкую цель
#4 тремя операциями: syntax, HIR и типы остаются следующими срезами карты.

## Ревизии и доказательства

Все ссылки на loupe ниже закреплены на
`371069c9312b8ddb4cc5045349937235218693f8`, как в `cjpm.lock`.
Проверены исходники именно этого Git-объекта, независимо от текущего HEAD cjls.
Уровни: **S** — source inspection; **C** — compile probe;
**R** — runtime probe; **U** — непроверенное требование к будущему адаптеру.
Уровень относится к утверждению, не ко всей строке или будущей реализации.

#6 считается завершённой по решению владельца проекта: `Reference.~init`
исправлен, краша больше нет. Это принятое исходное условие для #7, а не новая
runtime-проверка. Исторические результаты #6 доступны в
[отчёте на daa7368][runtime-audit]; его вывод о блокирующем краше предшествует
исправлению. Точный SHA исправления и повторные пробы здесь не устанавливаются.
`cjpm.lock` не меняется: оставшийся там `c66c1825…` не подтверждает наличие
исправления. Исторические G0–G10 нельзя автоматически переносить между ревизиями.

Для этой спецификации выбран ручной concrete facade и конвертация в обычные
Python dataclasses/tuple. Она не зависит от blanket `@DerivePython` чужих типов.
Наличие необходимых C API и безопасность trampoline ещё требуется проверить
на выбранной при реализации ревизии interop (**U**).

## Переменные и интерфейс контекста

Host запускает один скрипт в новом словаре globals/locals с `analysis`, `params`
и обычными builtins. Один и тот же словарь используется как globals и locals,
чтобы функции скрипта видели переменные. Решение об этом обходе опирается на
runtime-пробу `scope_function_adapter` #6 (**R**, исторический ded6e681).
Другие модули Python и внешние эффекты этим не изолируются.

`params` — read-only `Mapping[str, object]` (например `MappingProxyType`),
для этого среза с точным набором ключей:

```python
params = {"document": "file:///workspace/main.cj", "offset": 31}
```

`document` — абсолютный URI существующего документа в подготовленной сессии,
не путь, не FileId; `offset` — целое смещение UTF-8 в его исходном тексте.
Оба ключа обязательны даже для скрипта, запрашивающего только diagnostics.
Это один минимальный вход для примера и трёх операций; дальнейшие скрипты могут
иметь другие параметры по отдельному контракту. Host проверяет ключи и типы
до запуска. `Params` в stub — TypedDict формы данных, runtime-объект остаётся
read-only mapping. В нём нет управляющих callbacks или нативных указателей.

Все три свойства `Analysis` read-only и доступны как скопированные метаданные
даже после инвалидирования:

| Python | Значение и реализация | Уровень |
|---|---|---|
| `session_id: str` | Непереиспользуемый ID внешней сессии, одинаковый у её запросов | U, wrapper |
| `context_id: str` | Уникальный ID одного запуска, не адрес и не calca ID | U, wrapper |
| `revision: int` | Монотонный счётчик опубликованных изменений сессии, захваченный при создании; не сырой calca revision | U, wrapper |

Методы и helper entries:

| Python signature | Cangjie путь и правила | Доказательство и стратегия |
|---|---|---|
| `check_cancelled(self) -> None` | `calca.Database.unwindIfCancelled(): Unit`, реализовано через `storage.unwindIfCancelled()`; дополнительно флаг host и проверка lifetime | [storage][storage] S; manual binding U |
| `document(self, uri: str, /) -> Document` | `loupe.vfs.VfsPath.fromUri(uri: String): VfsPath`; `PathInterner.lookup(path: VfsPath): ?FileId`; lookup присутствия в захваченном состоянии VFS | [path][path], [vfs][vfs] S; validating wrapper U |
| `text(self, document: Document, /, *, range: ByteRange \| None = None) -> str` | Проверка Document, затем `AnalysisDatabase.sourceFile(fileId: FileId): ?SourceFile`, `SourceFile.text(db)` (generated @CalcaInput accessor); Rope → копия UTF-8 текста, при range — срез по байтам | [db][db] S; converter/manual binding U; generated accessor здесь не compile-probed |

Host получает `AnalysisDatabase.snapshot(cancelledBy!: () -> Bool = {=> false}): AnalysisDatabase`
из `loupe.db` ([db][db], **S**), под своей координацией с записью. Снимок не
экспортируется как Python database. Callback создаётся в Cangjie и обращается
к состоянию host, не удерживает Python callable. Один handle используется
одним исполнителем; параллельные вызовы одного `analysis` отклоняются
`AnalysisError`, а не запускают concurrent queries на нём (**U**).

`document()` не открывает файл с диска и не добавляет его в базу. Для URI host
сначала проверяет абсолютную схему и запрещает NUL, затем применяет нормализацию
`VfsPath`; malformed `file:` URI отклоняется `ValueError`, хотя upstream может
превратить его в virtual path. Нормализованный URI выдаётся через
`PathInterner.path(id: FileId): VfsPath` и `VfsPath.toUri(): String` (**S**).
Точное сопоставление URI с документом — по VfsPath, без самостоятельного
lowercase всего пути или разрешения symlink в Python. Виртуальные URI допустимы,
если их знает сессия.

## Подробная карта трёх операций

Все следующие функции — top-level пакет **`loupe`**, database из **`loupe.db`**,
FileId из **`loupe.vfs`**. Имена Python намеренно отделены от upstream.

| Python | Точная Cangjie signature | Вход → вызов → выход | Уровень и стратегия |
|---|---|---|---|
| `hover(self, document: Document, offset: int, /) -> Hover \| None` | `public func hoverAt(db: AnalysisDatabase, fileId: FileId, offset: Int64): ?HoverResult` | Проверить контекст, Document и byte offset; взять FileId из таблицы владельца; вызвать на snapshot; `None` → `None`, `Some` → `Hover(origin, range, tuple(items))`; повторно проверить отмену | [hover][hover] S; concrete wrapper, recursive converter и manual binding U |
| `diagnostics(self, document: Document, /) -> tuple[Diagnostic, ...]` | `public func diagnostics(db: AnalysisDatabase, fileId: FileId): Array<Diagnostic>` | Те же проверки без offset; вызвать на snapshot; скопировать массив, enum и вложенные ranges, добавить source origin; повторно проверить отмену | [diagnostics][diagnostics] S; wrapper, enum converter, manual binding U |
| `definition(self, document: Document, offset: int, /) -> tuple[NavigationTarget, ...]` | `public func definitionAt(db: AnalysisDatabase, fileId: FileId, offset: Int64): Array<NavigationTarget>` | Проверить вход; вызвать на snapshot; для каждого target разрешить его FileId через path table, скопировать full/focus и origin с учётом expansion; повторно проверить отмену | [definition][definition] S; wrapper, navigation converter, manual binding U |

`hoverAt` возвращает несколько items при неоднозначности; сохраняются порядок и
все кандидаты. `code` — Cangjie без тела, `path` — путь декларации либо None,
`doc` — текст комментария либо None. Это не готовый Markdown. `None` и пустая
строка не смешиваются. Range относится к имени в запрошенном тексте (**S**).

Diagnostics сохраняют severity и `unnecessary`; Hint не становится Warning.
Upstream собирает lexer/parser, conditional/scope, macro и inference результаты;
общий путь сортирует стабильно по началу range, inactive-file путь возвращает
свою последовательность. Адаптер сохраняет порядок, дубликаты и пустые ranges,
не добавляет выдуманные error codes. Это анализ loupe с текущей загрузкой проекта,
а не обещание полного набора ошибок компилятора. Макродиагностики уже
спроецированы upstream в источник либо на head вызова, повторно их не маппировать
([diagnostics][diagnostics], **S**).

Definition сохраняет все targets и порядок без дедупликации. Отсутствующий source
для binary declaration может дать пустой массив; это нормальное отсутствие
навигации, не ошибка доступа к документу ([definition][definition], **S**).

## Значения и преобразования в обе стороны

Все результаты — frozen dataclasses со slots, определённые в stub; containers —
Python tuples. Это обычные Python значения без proxy registry, setters и методов,
которые запрашивают базу. Равенство структурное; Python `is` не гарантируется.
Поля всегда присутствуют, включая None. Гарантии immutable относятся к обычному
API, не к обходу Python средствами introspection.

| Значение и исходная форма | CJ → Python | Python → CJ | Стратегия и доказательство |
|---|---|---|---|
| `Int64`, `Bool`, `String` | Python int, bool, str, точное значение; UTF-8 length-aware, без NUL truncation | `type(offset) is int`, не bool; затем проверка Int64 и границ текста. URI — str без NUL; никогда не читать память по identity attribute | supported scalar declarations; точные validators и length-aware converter U; исторический #6 R подтверждает Unicode, но обнаруживает NUL loss |
| `?T` | None или рекурсивный T | None либо проверенный T; optional value не делает аргумент необязательным | explicit converter U; #6 R: ?String и ?Array<Entry>, не произвольные типы |
| `Array<T>` | Новый `tuple(convert(x) for x in array)`; пустой → `()` | Входных массивов у трёх операций нет; обратный binding не регистрировать | converter U; #6 R для Array<String>/Entry подтверждает только те native converters, не выбранный tuple output |
| `ginkgo.TextRange(start: Int64, end: Int64)` | `ByteRange(start, end)` | Для `text(range=...)`: проверить класс и оба поля, затем `TextRange(start, end)`; range отдельно не содержит документ | [range][range] S; concrete value converter U |
| `loupe.HoverItem(code: String, path!: ?String = None, doc!: ?String = None)` | `HoverItem(code, path, doc)` | output-only, обратный converter не нужен | [hover][hover] S; converter U |
| `loupe.HoverResult(range: TextRange, items: Array<HoverItem>)` | `Hover(origin, ByteRange(...), tuple(HoverItem(...)))` | output-only | [hover][hover] S; nested converter U |
| `loupe.Severity = Error \| Warning \| Hint` | строки `error`, `warning`, `hint`, exhaustive switch; неизвестный вариант — AnalysisError | output-only | [diagnostics][diagnostics] S; enum converter U, без derived enum |
| `loupe.Diagnostic(range: TextRange, severity: Severity, message: String, unnecessary!: Bool = false)` | `Diagnostic(origin, range, tag, message, unnecessary)` | output-only | [diagnostics][diagnostics] S; nested converter U |
| `loupe.NavigationTarget(fileId: FileId, fullRange: TextRange, focusRange: TextRange, expansion!: ?MacroCallId = None)` | `NavigationTarget(origin, full_range, focus_range)` | output-only, не принимать его за новую цель запроса | [definition][definition] S; context-aware converter U |
| `loupe.vfs.FileId(index: Int64)` | `Document(session_id, document_id, uri)`, через owner table | Проверить тип Document, session_id, document_id и URI на совпадение с owner table; затем взять FileId, не создавать его из Python int | [vfs][vfs] S; wrapper/manual mapping U |
| `Origin`, revision/context IDs | Полностью скопированные Python поля | Не принимаются методами этого среза | owner metadata wrapper U |

Для output-only DTO Python-конструктор допустим, но созданное значение не
получает доступа к базе. `ByteRange` проверяет собственный инвариант
`0 <= start <= end <= Int64.Max`; `Document` конструируем как данные, но каждый
вызов `Analysis` повторно сверяет его с таблицей. Наличие похожих полей или
`__cangjie_identity__` никогда не считается подтверждением типа/принадлежности.

Составные return values не возвращаются назад в CJ автоматически. Требование
двусторонней конвертации для каждого типа не означает ненужного общего
FromPy для Hover/Diagnostic/NavigationTarget. Здесь входы только URI, Document,
offset и optional ByteRange; их полный обратный путь определён выше.

## Идентичность и системы координат

Document — detached значение со стабильным ID пути внутри одной сессии, не
handle snapshot. `document_id` — непрозрачная строка, не публичный FileId.index;
внешний владелец не переиспользует её для другого пути. Один и тот же документ
можно использовать в следующем контексте той же сессии, если он существует.
Удаление и повторное создание того же пути сохраняет ID, но меняет revision;
rename — другой путь и другой ID. Document из другой сессии отвергается.
URI служит отображению и lookup, он не заменяет session identity.

Каждый результат содержит `Origin(document, revision, space, expansion_id)`.
`revision` обозначает ревизию контекста, на которой вычислены координаты,
не LSP document version. `space == "source"` требует `expansion_id is None`.
`space == "expansion"` требует непрозрачный ID раскрытия, уникальный в контексте
(например owner token с context_id), а `document` указывает файл вызова.
`MacroCallId` не выходит в Python: owner table назначает токен, пока контекст
валиден; скопированный ID после закрытия остаётся только меткой происхождения.
Он не обещает исторический lookup, повторное использование или semantic identity.

Все ranges полуоткрытые `[start, end)` в байтах UTF-8 соответствующего текста.
Offset допустим от 0 до byte length включительно, только на границе Unicode
scalar; EOF допустим, но не обязан давать результат. Range ограничен длиной
этого текста, его концы также на UTF-8 boundaries. `[n, n)` допустим.
Например, в `aя🙂` границы — 0, 1, 3, 7; offset 2 или 4 отвергается.
`text(document, range=...)` режет UTF-8 bytes до декодирования, не Python str
по символьным индексам; None означает весь текст. Линии и UTF-16 positions в
этот срез не входят. Основа range semantics — [TextRange][range] (**S**),
валидация UTF-8 boundaries — обязанность адаптера (**U**).

Для navigation оба диапазона относятся к одному origin;
`full_range.start <= focus_range.start <= focus_range.end <= full_range.end`.
Когда `NavigationTarget.expansion` пуст, origin — source. Когда непуст,
оба диапазона относятся к тексту `expandedMacro`, а не к тексту файла вызова.
Нельзя убрать tag и показать эти числа как source ranges. Upstream
`expansionTarget` уже маппирует скопированный focus в source, с fallback полного
range к focus; адаптер не выполняет повторное преобразование (**S**).
Сохранить expansion branch необходимо и при source-входе: внутренние пути
`bodySourceTarget`/`targetOf` могут вызвать `expansionTarget`.

В этом срезе входы `hover`, `diagnostics`, `definition`, `text` всегда source.
Раскрытие нельзя передать вместо Document. Будущие bindings могут использовать
точные upstream signatures (**S**, пакет loupe):

```cangjie
public func hoverInExpansion(db: AnalysisDatabase, call: MacroCallId, offset: Int64): ?HoverResult
public func definitionInExpansion(db: AnalysisDatabase, call: MacroCallId, offset: Int64): Array<NavigationTarget>
```

Они не регистрируются в этом срезе; нет обещания прочитать expansion text через
`text()`. Если target указывает в expansion, скрипт может только вывести его
происхождение и ranges. Доступ к тексту/структуре раскрытия — отдельная работа.

## Владение и завершение запроса

Внешний владелец удерживает корневую базу, VFS и project session между запросами.
Контекст содержит snapshot и owner state; Python facade держит только проверяемый
request token. Host закрывает token в finally на любом выходе и удаляет запись
snapshot/expansion table, когда завершились активные вызовы. Сохранённая Python
ссылка на facade не удерживает snapshot после завершения запроса и не продлевает
его логическую валидность. Facade нельзя конструировать, copy/deepcopy запрещены
TypeError; публичных close/release у него нет (**U**, manual binding).

Document и все DTO копируются поверхностно безопасно, поскольку всё дерево
содержит только immutable values. Они не удерживают native references; release
для них — обычный Python refcount/GC, без ожидаемого вызова CJ GC. Скопированные
значения остаются читаемыми после отмены и закрытия с исходной revision;
свежесть координат это не продлевает. `Document` не открывает исторический текст.

Изменения файлов, project model и ответы macro server могут отменить контекст.
Следующий вызов проверяет host token и calca cancellation до чтения и после
материализации; успешный результат одного вызова не гарантирует успех всего
скрипта. Перед публикацией ответа host ещё раз под координацией с записями
проверяет revision/cancel flag; stdout/result буферизуются. Перехват исключения
скриптом не разрешает публикацию результата отменённого запроса. Pure Python
между вызовами не прерывается немедленно. Автоповтора нет: повтор имеет новый
context и может повторить внешние эффекты. Storage snapshots отменяемые, не
исторические базы ([storage][storage], **S**); правила facade/публикации — **U**.

## Отсутствующие значения и ошибки

При нескольких проблемах порядок проверки: lifetime/cancellation, арность и
типы, принадлежность Document, существование, offset/range, вызов и conversion,
финальная cancellation check. При отмене/закрытии новый native read не начинается.

| Ситуация | Python поведение | Upstream и доказательство |
|---|---|---|
| Нет hover на корректном месте | `None` | `hoverAt`: ?HoverResult, S |
| Нет definitions или diagnostics | `()`, не None | обе функции возвращают arrays, S |
| Неверная арность/тип, bool вместо offset, неверный range class | `TypeError` до native dispatch | U; #6 R обнаруживает SystemError без такого boundary |
| Offset вне Int64/текста, отрицательный/середина UTF-8, некорректный range/URI, лишние ключи params | `ValueError` | U; TextRange проверяет только часть инвариантов, S |
| Нет обязательного ключа params | Host отклоняет с `ValueError` до исполнения | U |
| URI неизвестен, документ удалён или не загружен для source analysis | `DocumentNotFoundError` | U, существование в captured owner state, не live VFS |
| Document другой сессии | `ForeignContextError` | U; значения FileId без owner этого не различают |
| Подделанный/неизвестный ID или URI, не совпадающий с ID в своей сессии | `ValueError` | U, lookup owner table без чтения proxy storage |
| База/макросы изменились, host отменил или calca бросил CancelledException | `AnalysisCancelledError`; весь ответ отбрасывается | [exception][exception], [db][db] S для calca; перевод U |
| Метод после завершения запроса | `StaleContextError`; метаданные и DTO читаемы | U; это не отсутствие hover |
| Внутренняя ошибка CJ, неверный результат conversion | `AnalysisError`; успешный результат не публикуется | U, требуется exception boundary |

Удаление нельзя проверять только `sourceFile`: upstream навсегда сохраняет input
по FileId и при `applyChanges` ставит удалённому файлу пустой Rope; неизвестный
FileId возвращает None/пустой массив у этих трёх операций ([db][db], **S**).
Нужен согласованный с snapshot снимок присутствия/загрузки файлов. Пустой
существующий документ при этом корректен: hover None, definition `()`, diagnostics
— результат upstream без синтетического «file deleted». Если документ удалён
после создания snapshot, текущий запрос отменяется, а свежий получает not found.

Все CJ exceptions перехватываются внутри Cangjie до возврата через C callback.
Ручной trampoline устанавливает Python exception и возвращает согласованный
ошибочный C API result; никакое исключение не проходит через C ABI. Python
validation не заменяет эту границу. При conversion failure освобождаются
частично созданные owned refs под GIL. Весь Python C API, включая release,
исполняется с GIL; один interpreter lifetime на процесс, без unload/reload при
живых wrappers. Это требования реализации (**U**), не следствие одного
исправления финализатора.

## Пример и ожидаемая форма

Для [скрипта](../examples/initial_analysis.py) host подготавливает один документ
`file:///workspace/main.cj` в source package `m`, без CRLF, с текстом:

```cangjie
package m
class C {}
func f(x: C): Unit {}
```

Параметры: `{"document": "file:///workspace/main.cj", "offset": 31}`.
`C` в типе параметра занимает bytes `[31, 32)`, имя класса `[16, 17)`, весь
class node `[10, 20)`. При revision 12 ожидается Python значение:

```python
{
    "revision": 12,
    "hover": {
        "range": (31, 32),
        "items": [{"code": "class C", "path": "m", "doc": None}],
    },
    "diagnostics": [],
    "definitions": [{
        "document": "file:///workspace/main.cj",
        "revision": 12,
        "space": "source",
        "expansion_id": None,
        "full_range": (10, 20),
        "focus_range": (16, 17),
    }],
}
```

Форма и offsets проверяются локально на Python; semantic значения — ожидаемые
по source inspection (**S**) и предложенному API (**U**), не runtime-проба
биндинга. Фикстура предполагает загруженную модель `m` и доступный Unit/prelude;
при другой конфигурации diagnostics могут отличаться. Upstream tests
[hover_test][hover-test] и [definition_test][definition-test] показывают
аналогичные проверки, но здесь не запускались. В примере списки/словарь — явная
проекция скрипта, результаты API остаются tuple/dataclasses. Host читает
`result` только после своей финальной проверки; это не MCP response schema.

## Оставшиеся interop ограничения

Эти пункты не возвращают #6 в работу; это отдельные проверки и работа реализации
контракта на выбранной ревизии. Исторический audit на ded6e681 даёт **R/C**
только перечисленным там случаям; текущее состояние исправлений здесь **U**.

- Нужен exception trampoline с проверкой типа до storage lookup. Исторические
  G9/ошибки callback нельзя исправить только проверкой params в Python.
- Нужны length-aware String converters для NUL в исходном тексте, doc и message.
  Для URI NUL запрещён; для `text()` и результатов молчаливая потеря недопустима.
- Нужна проверка balanced refs, освобождения facade registry и закрытия контекста
  с сохранённой Python ссылкой. Исправление `Reference.~init` принято, registry
  и callback retention автоматически из него не следуют.
- Concrete dataclasses создаются вручную; enum tags и tuple containers не
  используют проблемные исторические G3/G4. Defaults `text(range=None)` задаёт
  Python wrapper явно, без зависимости от G2. Python callbacks, generic export
  и mutable CJ structs для этого среза не требуются.
- Перед реализацией надо закрепить точную исправленную interop revision и
  проверить этот facade целиком; старый lock не является такой проверкой.

## Недостающие нейтральные upstream API

Это отдельные пробелы loupe/host, а не общие дефекты Python interop:

- В `AnalysisDatabase` нет признака «удалён» и snapshot присутствия VFS.
  Для текущего контракта достаточно external owner table, согласованной с revision;
  добавление такой нейтральной модели upstream — возможное упрощение.
- Текущий срез не выдаёт summary полноты загрузки/ожидаемых macro outputs.
  Empty diagnostics не означает, что macro server уже ответил. Нейтральное
  coverage/readiness API нужно определить отдельно перед таким обещанием.
- Detached expansion ID не предоставляет текста и source map. Отдельному
  expansion/syntax срезу нужны lookup через актуальный контекст и явный mapping;
  существующие `hoverInExpansion`/`definitionInExpansion` нельзя принимать за
  готовый безопасный Python handle API.

Проверка перед реализацией должна покрыть Unicode/EOF/пустой файл, несколько
hover candidates, все severity, межфайловый и expansion target, deleted против
empty, foreign Document, смену revision между вызовами и перед публикацией,
закрытие с сохранёнными DTO/facade и ошибочный CJ callback. Эти проверки не
подменяются проверкой синтаксиса stub или примером с test double.

[runtime-audit]: https://github.com/ide4cj/cjmcp/blob/daa7368b74a474f15cc83d23ce2922bdc49c0c89/docs/py-interop-runtime-audit.md
[db]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/db/db.cj
[vfs]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/vfs.cj
[path]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/path.cj
[range]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/ginkgo/src/text_range.cj
[storage]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/calca/src/storage.cj
[exception]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/calca/src/exception.cj
[hover]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hover.cj
[diagnostics]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/diagnostics.cj
[definition]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/definition.cj
[hover-test]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/hover_test.cj
[definition-test]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/definition_test.cj
