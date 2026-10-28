# Карта API cjmcp и ограничений DerivePython

Основа реализации — небольшой Cangjie-фасад над `loupe`, владеющий проектом,
VFS и базой анализа, с явным преобразованием результатов для Python.
**В закреплённой версии нет подтверждённого прямого экспорта через
`@DerivePython` из отдельного пакета: даже минимальные функция и структура
не компилируются.** Сначала нужен ремонт границы генератор/runtime (G0).
После него простые значения подходят для генерации; состояние анализа,
интернированные идентификаторы и загрузка проекта требуют адаптеров.

## Версии и границы карты

Срез на 2026-10-28:

| Компонент | Проверенная версия |
|---|---|
| cjmcp | `3e070a6`, исходные `cjpm.lock` и `modules/loupe4py/cjpm.toml` |
| cjls, включая loupe и project_model | `371069c9312b8ddb4cc5045349937235218693f8`, из lock-файла |
| py_interop | `c66c1825df7f8eff95244fce4cdc8f273a215dd7`, из lock-файла |
| Компилятор проб | `1.3.0-alpha.20261014001050`, Linux x86_64, cjnative |

Локальный кэш `py_interop` на `9bc5878` и текущий checkout cjls не являются
этим срезом. В частности, наличие `@PyIgnore`, callback readers и исправлений
enum в более новом кэше не означает их наличие в зависимости cjmcp.

Карта охватывает 139 явно объявленных публичных сущностей корневого пакета
`loupe`, пакетов `loupe.db`, `loupe.vfs` и `project_model`. Из остальных пакетов
включены типы на этой границе и нужные операции над текстом. Внутренний публичный
HIR/AST API целиком не предлагается экспортировать: его граница описана отдельно.
Сгенерированные `@CalcaInput`/`@CalcaInterned` члены нельзя считать обычными
полями исходных деклараций.

`project_model` нужен для работы с реальным проектом, но пока не указан в
зависимостях `loupe4py`: он зависит от `loupe`, а не наоборот. При добавлении
его следует закрепить на той же ревизии cjls. Аналогично явно объявить пакеты,
которые фасад импортирует непосредственно, вместо расчёта на транзитивные импорты.
[Манифесты loupe][loupe-manifest] и [project_model][project-manifest].

Обозначения в таблицах:

- **D** — форма декларации/значения поддерживается генератором по исходникам;
  для новых деклараций в `loupe4py` всё равно требуется G0 и проверка исполнения.
- **A** — адаптер в cjmcp: обёртка функции, конкретный класс-фасад,
  DTO (отдельный тип результата), преобразование или ограничение времени жизни.
- **G** — доработка генератора/runtime для сохранения исходного API.
  Номер указывает на конкретный пункт ниже; это не всегда препятствие для A.

**D не означает, что импортированный тип уже экспортирован.** Макрос получает
декларацию, а не метаданные импортированного пакета. Нельзя аннотировать `import`
или получить все методы через пустой `extend`. В текущем cjmcp
`loupe4py.cj` содержит только `package loupe4py`: Python API ещё не реализован.

## Что поддерживает механизм преобразования

[Диспетчер макроса][generator] принимает `class`, `struct`, `enum`, `extend`
и свободную `func`. `interface`, `type` и глобальные переменные не входят в
этот список. Поддержка узла AST ещё не означает корректный код для любого типа.

| Форма | Направление и ограничение | Решение для cjmcp |
|---|---|---|
| `String`, `Bool`, целые, `Float32/64`, `Rune`, `Unit` | Есть `IntoPy` и `FromPy`; обычный вызов `toPyObj(String)` компилируется без макроса | D для значений; диапазоны чисел проверять на границе |
| `?T` / `Option<T>` | Reader рекурсивный; `None` соответствует Python `None`; вывод требует `T <: IntoPy` | D при поддержанном T; не смешивать отсутствие результата и ошибку |
| `Array<T>` | Reader рекурсивный; вывод через `PyList`, ограничение `T <: PyFFIType` | D для поддержанных элементов; `Array<Byte>` не обещает Python `bytes` |
| `(A,B)` | Есть reader и отдельные перегрузки вывода, также для `?(A,B)` | D только для поддержанных компонентов |
| `(A,B,C)` | Генератор выбирает reader, но reader проверяет `size != 2` | G4: исправить чтение тройки; до этого A |
| Кортежи большей арности; вложенные комбинации | Нет общего решения; отдельная перегрузка вывода пары не даёт ей `IntoPy` для произвольного контейнера | A: именованные DTO; G4 для полного обобщения |
| `HashMap<K,V>`, `HashSet<T>`, `Range<T>` | Есть вывод с ограничениями, но нет симметричного `FromPy` для этих типов в закреплённом `cjobj.cj` | A: массивы пар/значений; не заявлять двустороннюю поддержку |
| `ArrayList<T>` | Есть reader через `FromPy`, нет аналогичного `IntoPy` в `cjobj.cj` | A: `toArray()` на выходе; изменение списка в CJ не считать изменением Python list |
| Конкретные class/struct с доступным конструктором и поддержанными членами | Генерируются proxy, `IntoPy`, `FromPy`, `pyClass()` | D по форме; G0; для чужой декларации A или G1 |
| Enum | Есть Python-классы вариантов, но неполная реализация преобразования и ошибка конструкторов | A: явный тег и поля; G3 для исходного enum |
| Функциональные типы, например `() -> Bool` | В закреплённом reader нет ветки `FuncType` | A: замыкание создаётся внутри CJ; G5 для Python callback |
| Generic class/struct, generic методы | Генерация использует голый `identifier`, не переносит параметры и ограничения | A: конкретные специализации; G6 для общего API |
| `Iterator`, `Iterable`, `Path`, `DateTime`, `Storage`, AST-узлы | Нет автоматического рекурсивного экспорта чужих типов | A: материализовать нужную часть или держать внутри фасада |

Основание: [конвертеры и readers][converters], включая отдельные перегрузки
кортежей. Доступность преобразования в одном направлении не доказывает
поддержку обратного направления, сеттера или вложенного контейнера.

## Loupe и результаты запросов

Все функции в таблице публичны на закреплённой ревизии. Для их экспорта из
`loupe4py` нужен хотя бы forwarding-вызов: аннотация в другом пакете не меняет
объявление функции в loupe. Для запросов фасад дополнительно выбирает snapshot,
переводит путь в `FileId`, проверяет позицию и материализует результат.

| Публичные функции | Результат и зависимости | Экспорт |
|---|---|---|
| `hoverAt`, `hoverInExpansion` | `?HoverResult`: `TextRange`, `Array<HoverItem>`; у `HoverItem` `code`, `path`, `doc` | A для запроса; форма DTO — D. Expansion принимает проверенный токен, не сырой `MacroCallId` |
| `definitionAt`, `definitionInExpansion`, `implementationsAt` | `Array<NavigationTarget>`: файл, полный/фокусный диапазоны, `?MacroCallId` | A: URI/путь и диапазоны, отдельный токен expansion |
| `findReferences`, `highlightRelated` | `Reference`, `RelatedHighlight`, `?ReferenceAccess`, флаг объявления | A: `ReferenceAccess` как тег; `loupe.Reference` импортировать с alias из-за `py_interop.Reference` |
| `diagnostics` | `Diagnostic`: range, `Severity`, message, `unnecessary` | A: severity как тег; значения полей сохранять, включая пустой диапазон |
| `fileStructure`, `fileSymbols`, `workspaceSymbols` | `StructureNode` (рекурсивные children), `FileSymbol`, `FoundSymbol`, `StructureKind` | A: дерево/массив DTO; файлы и лимит задаёт фасад; `fileSymbols` требует `SourceFile`, остальные — `FileId` |
| `completionsAt`, `completionDetails` | `CompletionResult`, `CompletionItem`, `CompletionKind`, `CompletionSource`, `CompletionOverload` | A: label/kind/relevance/overloadCount плюс токен для details; source содержит HIR-ссылки |
| `foldingRanges` | `Fold`, `FoldKind`, `TextRange` | A для запроса и enum; DTO диапазона — D |
| `extendSelection` | `Array<TextRange>` | A для запроса; DTO диапазона — D |
| `highlight` | `HighlightedRange`, `HighlightTag`, `HighlightModifiers`, `HighlightModifier`; именованный `range!: ?TextRange = None` | A: явные теги/флаги; default задаёт обёртка; G2 при сохранении исходной сигнатуры |
| `formatting`, `rangeFormatting` | `?Array<TextEdit>`; re-export `cjformat.TextEdit` | A: диапазоны и replacement; `None` отдельно от пустого списка |
| `macroCallAt`, `expandedMacro` | `MacroCallAt`, `ExpandedMacro`, `ExpansionKind`, `MacroCallId`; default `inBody` | A: токен вызова, текст, диапазоны, kind/declaration; G2/G3 для исходной формы |
| `expandFile` | `ExpandedFile`, `ExpandedSegment`, `ExpandedOrigin`, `ExpandedPlace`, `ShownExpansion` | A: текст и source map; методы отображения позиций выполняются в CJ |
| `newFilePackageLine` | `ProjectModel`, `VfsPath`, callback `(VfsPath) -> ?Rope`, результат `?String` | A: lookup текста из принадлежащего фасаду VFS; callback наружу требует G5 |
| `builtinTypeDoc`, `builtinAnnotationDoc`, `builtinMacroDoc` | `?BuiltinDoc`: name, code, summary — строки | A: forwarding и DTO; вся форма результата — D |

[Исходники корневого пакета loupe][loupe-src]. Ни одна строка не требует
экспорта всего `loupe.hir` ради результата запроса.

Дополнительные публичные типы и члены, влияющие на границу:

| Сущности | Что сохранять / почему нужен адаптер |
|---|---|
| `Definition` | Варианты несут `DefId`, `LocalId`, `TypeTarget`, `PackageRef`. A: раскрывать только через нужный запрос. G3 и экспорт HIR понадобятся для буквального enum |
| `CompletionSource`, `CompletionOverload` | `DefId`, `?Ty`, `LocalId`, массив перегрузок; нельзя реконструировать из произвольных чисел клиента. A: ограниченный по времени токен или eager details |
| `HighlightModifiers` | Наружу отдавать именованные флаги; операции над битами и enum выполнять в CJ |
| `ShownExpansion` | `text`, `toWritten`, обе перегрузки `fromWritten`. A: отдельные имена для offset/range и проверка границ |
| `ExpandedFile` | `text`, `segments`, `placeOf`, `fromSource`, `fromExpansion`, `expansionOf`. A: сохранение контекста snapshot для токенов и отображения диапазонов |
| `TextRange`, `TextEdit` | Публичные re-export из ginkgo/cjformat не создают Python bindings. A: локальные DTO; G1 для привязки исходных типов |

`StructureNode` и `ExpandedFile` имеют конструкторы без `public`: фильтр
генератора «не private» не является фильтром публичного API. Перечень выше
описывает доступный контракт, а не предлагает экспортировать все члены,
которые макрос случайно увидит.

## База анализа, VFS и модель проекта

| Пакет и публичные сущности | Прямо пригодная форма | Нужный адаптер / блокер |
|---|---|---|
| `loupe.db.AnalysisDatabase` | Отдельные результаты `sourceFile`, `project`, `binaryStamp` — optional | A: закрытый владелец базы. `storage: Storage`, `batch<T>`, callback у `snapshot`, `Rope`, `Durability` и defaults исключают blanket derive; G2/G3/G5/G6 при полном экспорте |
| `SourceFile`, `Project`, `Module`, `Package`, `BinaryPackageFile` | Идентичность input | A: обращаться через database; `@CalcaInput` генерирует getters/setters с db и durability, это не изменяемые Python-поля |
| `CfgOption`, `Cfg` | String-пары; `Cfg(Array<(String,String)>)`, `get`, `overriddenBy` | A: concrete DTO/конвертер; форма D после G0/G1. Input массива пар имеет reader, вывод `options` — массив `CfgOption` |
| `PackageModel`, `InactiveFile`, `ModuleModel`, `BinaryPackage`, `BinarySources`, `BinaryModel`, `ProjectModel` | Конкретные записи и массивы | A: пути, конфигурация и enum; defaults G2. `ModuleModel.durability` — `calca.Durability` |
| `ProjectModel.files`, `binarySourceFiles`, `covers`, `merge`, `packageOfNewFile`, `cjoFiles` | Запросы к модели | A: вызываются владельцем проекта; выводить строки/DTO файлов |
| `BinarySourceFile`, `InactiveSourceFile` | Метаданные файлов | A: заменять внутренние ссылки на пути/DTO; `BinarySourceFile.context` связывает запись с `Package` |
| `SpanOrigin`, `MappedSpan`, `MappedText` | Диапазоны и исходный текст, `fromSource`, `originOf` | A: явная tagged source map; G3 для enum, G1 для исходных типов |
| `MacroItemValue`, `MacroItem`, `MacroSeverity`, `MacroDiagnostic`, `MacroOutput` | Значения ответа macro server | A: tags/DTO; `MacroOutput.after` оставить внутри CJ. Не запускать macro server самим фактом экспорта типа |
| `MacroCallKey`, `MacroOutputs` | Ключ, `get`, `withOutput`, `size` | A: часть владельца проекта; default `inBody` требует G2 для точного API |
| `loupe.vfs.FileId`, `ChangeKind`, `ChangedFile` | `FileId.index: Int64` — D; enum — G3 | A: file ID относится к конкретному `PathInterner`; внешнее имя — путь/URI, не произвольный integer |
| `PathInterner` | `lookup`, `intern`, `path` | A: держать внутри session; не делить идентификаторы между независимыми владельцами |
| `Vfs` | `paths`, `fileId`, `filePath`, `fileContents`, `files`, `setFileContents`, `takeChanges` | A: String ↔ Rope, удаление через `None`, изменения применяются к root database |
| `VfsPath` | `file(String)`, `virtual`, `fromUri`, `toUri`, `name`, `parent`, `join`, `isUnder`, `segmentsUnder`, сравнение/hash | A: явная строковая граница. `file(Path)`, `filePath: ?Path`, закрытый конструктор мешают общему derive; нужны G1/G7/G8 |
| `RootsRead`, `readRoots`, `readFiles`, `readFile` | Загрузка файлов | A: `RootsRead.files: Array<(VfsPath,Rope)>` → массив DTO; сохранять truncated; явный бюджет вместо default `Int64.Max`; G2 для исходной сигнатуры |
| `isWorkspaceFile`, `isWorkspaceDirectory` | Bool, но входы `VfsPath` | A: строки → VfsPath |
| `isScanned`, `isCangjieFile` | `String -> Bool` | D по сигнатуре; A forwarding или G1 для привязки существующей функции, плюс G0 |
| `FileStamp`, `CjoFile`, `CjoFileRead`, `CjoRead`, `cjoFilesIn`, `readCjoFiles` | Двоичные входы анализа | A: сохранять size/problems/truncated; `DateTime`, пути, bytes и callback `unchanged` внутри CJ; G2/G5 при исходном API |

Источники: [database][database], [модель и Calca inputs][db-project],
[результаты макросов][macro-output], [VFS][vfs], [пути][paths], [загрузчик][loader].

`AnalysisDatabase` следует скрыть за владельцем, который явно связывает
`setFileText`, `applyChanges`, `setProject` и `batch` с root handle, а запросы —
со snapshot. `snapshot(cancelledBy: ...)` создаёт другой handle, не копию всей
модели. Для удаления файла сохраняется идентичность, его текст в базе становится
пустым. Кэши completion/expansion должны освобождаться и инвалидироваться при
смене ревизии; долгоживущие ответы не должны удерживать произвольные AST-деревья.
[Правила анализа A4–A6, A9, A13, A16, A21][analysis-rules].

## Project model и вспомогательные пакеты

| Публичные сущности project_model | Экспорт и причина |
|---|---|
| `findProject`, `findProjects`, `loadCjpmProject`, `loadProjectJson`, `looseProject`, `loneFileProjects`, `projectDirOf` | A: фасад принимает пути/config, создаёт CJ callback `env`, возвращает model summary и problems. G2/G5 для исходных defaults/callbacks |
| `lowerProjectJson`, `toProjectJson`, `prettyProjectJson`, `packagesUnder` | A: внутреннее преобразование и снимок конфигурации; не превращать JSON-типы автоматически в публичный MCP protocol |
| `ProjectJson`, `ModuleJson`, `InactiveFileJson`, `PackageJson`, `BinaryJson` | A: DTO или JSON String; аннотированные сериализацией члены требуют проверки G8, зависимые значения — конвертеров |
| `ProjectLoad`, `ProjectSource` | A: модель, источник, путь, problems и флаг partial; enum → тег, G3 при прямом экспорте |
| `ProjectException` | A: перевести в ошибку загрузки; это не обычный экспортируемый класс, G9 |
| `CangjieHome`, `CangjieSrc`, `findCangjieHome`, `findCangjieSrc` | A: SDK paths/options, env callback создаётся внутри CJ |
| `withCangjieHome`, `withCangjieSrc` | Возвращают функции `(String) -> ?String`; оставить внутри CJ. G5 для полного двустороннего callback API |
| `hostCfg`, `sdkTarget` | A: `Cfg` ↔ DTO; optional target сохраняется |
| `withPackageCfgs`, `expandPath` | A: `ArrayList<String>` для накопления problems не переносится как Python out-parameter; возвращать problems явно |
| `PROJECT_JSON`, `CFG_TOML` | Строковые константы имён файлов. A: явная регистрация значений; макрос не принимает const |
| `moduleOf` | D: `String -> String`; A forwarding и G0 |
| `declaresMain`, `packageHeader` | D по сигнатурам `Array<Byte> -> Bool/?String`; A при Python String/bytes, явный UTF-8 |

[Исходники project_model][project-src].

| Пакет | Что действительно нужно cjmcp | Что оставить внутри / работа генератора |
|---|---|---|
| `ginkgo` | `TextRange(start,end)`, `at`, `empty`, `len`, `isEmpty`, `contains`, `containsInclusive`, `containsRange`, `intersect`, `cover`, `shift`, сравнение/hash — кандидаты D по форме | A/G1 для исходного типа; `SyntaxNode<K>`, `SyntaxToken<K>`, `Parse<K>`, `SyntaxNodePtr<K>`, `AstPtr<K,N>`, builders, iterators — A; G6 для общего API |
| `rope` | A: `Rope` ↔ String, `LineColumn` ↔ два числа, `Encoding` ↔ явный тег | Методы Rope и `PositionCursor` исполнять в CJ. `TextSummary` с `EMPTY`, enum и операторами — не blanket D |
| `cjformat` | `TextEdit` — DTO; `formatText(String): ?String` — D по сигнатуре | A forwarding; `format`, `formatRange` принимают `CjParse`; `applyEdits` требует конвертера `TextEdit` |
| `cjsyntax`, `cjsyntax.ast`, `loupe.syntax` | При отдельном syntax tool — A: текст/ошибки/ограниченное представление дерева | `CjParse`/`CjSyntaxNode` и другие aliases — G1/G6, `loupe.syntax.parse` требует db и SourceFile; typed AST, generic iterators не выставлять транзитивно |
| `loupe.hir` | Только значения, достижимые из результатов: `MacroCallId`, `DefId`, `Ty`, `LocalId`, `TypeTarget`, `PackageRef` | A: токен с владельцем/ревизией либо материализация; `Ty.text(db)` вычислять до выдачи. `Ty`/`MacroCallId` — `@CalcaInterned`; полное HIR API требует отдельной карты |
| `calca` | Внутренние `Database`, `Storage`, durability и отмена | A: корректная модель snapshot/write и ошибки. Generic storage/query API и макросы не нужны Python |
| `cjo`, `fbs`, `index_map` | Чтение `.cjo`, внутренние таблицы и идентификаторы | Оставить в CJ; flatbuffer views/generics/время жизни буферов не выводить на границу |
| `platform`, `stdxx`, `fjson`, `ftoml` | Файлы, окружение и загрузка конфигурации | Внутренние зависимости; публичность их API в CJ не является основанием экспортировать его в Python |

## Доработки генератора и runtime

| Код | Подтверждение и требуемое изменение | Влияние / обход |
|---|---|---|
| **G0** | Пробы отдельного пакета: scalar падает на `PyObj(Reference(...))`; record — в том числе на `NativePyObj`, `PyType`. Эти constructor/type/class непубличны. Нужен публичный стабильный bridge API либо генерация только через доступные операции; перепроверить остальные диагностики после первичных исправлений | P0 для любого `@DerivePython` в loupe4py. Сборка самой библиотеки не проверяет внешнее применение макроса |
| **G1** | `ExtendGenerator.generate` добавляет члены в `T__PyInteropNativeDescriptor`, но не создаёт descriptor/`IntoPy`/`FromPy`; проба extend на ранее необёрнутом типе падает. Нет поиска деклараций по import, пакетного экспорта или обработки aliases | Для точного API нужен отдельный механизм binding чужих типов/функций. Для фасада достаточно A: локальные concrete wrappers; не добавлять py_interop во все upstream-модули |
| **G2** | `doArgsCheck` требует точное число positional/keyword args; default выражения не используются. В expansion пробы `limit! = 5` обязательно `PyDict_Size(kwargs) == 1` | Python defaults делает A. Если сохранять исходный API — разбирать обязательные/необязательные args; `?T` не делает аргумент необязательным |
| **G3** | Enum `emitExtendPython` не добавляет `IntoPy & FromPy<T>` и readers, в отличие от class/struct. `toPyObj()` создаёт proxy базового enum-класса; `kind` у варианта возвращает имя enum, не варианта. `makeFakeClass` не увеличивает `index`: вариант с двумя payload-полями падает при macro expansion | A: tags/DTO. Исправить conversions, выбор variant class, tag, нумерацию полей; проверить значения, пришедшие из CJ, а не только Python constructors |
| **G4** | `PyInteropTupleReader3` проверяет размер 2, затем читает элемент 2; общего tuple converter нет | Исправить reader и проверить композицию с Option/Array. A: именованные DTO |
| **G5** | `constructReaderForType` не обрабатывает `FuncType`; callback-проба не удовлетворяет `FromPy`. Возврат CJ-функций также не имеет общего конвертера | A: env/cancelledBy/textOf/unchanged создаются внутри CJ. Общая поддержка требует GIL, владения callable, времени жизни и перевода исключений |
| **G6** | Используется имя без generic arguments/constraints; проба `Box<T>` оставляет неизвестный T и голый Box. Обработка generic методов также не переносит их параметры | A: concrete API; поддержка monomorphization/interface dispatch — отдельная работа, не prerequisite для MCP |
| **G7** | Из списка init исключаются private, затем при отсутствии init синтезируется `init(){}`; проба типа с private constructor падает. Setter использует `let selfCJ` и присваивание; struct получается из registry как значение | Нужен запрет Python construction для output-only типов, режим factories и корректный write-back mutable structs. A: immutable DTO/закрытое состояние; mutable struct поведение требует отдельной runtime-пробы |
| **G8** | Фильтруется только `private`; нет `@PyIgnore` и разворачивания `MacroExpandDecl` в закреплённом диспетчере. Нет автоматического экспорта inherited API; static fields/properties проходят через instance getters. Перегрузки методов перебираются; static-флаг берётся из первой перегрузки | Нужны явная selection/rename policy, macro composition, политика mixed static/instance overloads. A: обёртки с уникальными именами и точно выбранными членами |
| **G9** | В генерируемых callbacks нет общего exception boundary. `PyProxy.getFromRegistry(ptr)` читает registryId без проверки Python-типа; top-level function при несовпадении аргументов возвращает NULL без установки ошибки | P0 перед внешними вызовами: проверять тип до чтения storage, устанавливать Python exception на каждой ошибке, не выпускать CJ exception через C ABI. Адаптеру нужен единый проверенный trampoline, не повторение небезопасного кода макроса |
| **G10** | Макрос создаёт `pyClass()` и свойства `PythonTopLevelFunctions`; пример вручную кладёт их в `PyDict` после `Python.load()` | Нужна отдельная регистрация модуля и запуск. `@DerivePython` не создаёт автоматически импортируемый CPython extension и не реализует MCP transport |

G0–G8 подтверждены исходниками; перечисленные ниже compile-пробы дополнительно
подтверждают конкретные отказы. Риски G9 выявлены по коду, без запуска ошибочных
FFI-вызовов. Пример и build script ориентированы на embedded Python; наличие
`output-type = "dynamic"` само по себе не даёт `import loupe4py`.
[Generator][generator], [runtime conversions][converters], [proxy storage][proxy],
[PyObj][pyobj], [пример][example], [build script][interop-build].

## Проверки и порядок реализации

`cjpm build` исходного py_interop на закреплённой ревизии завершился успешно.
[Скрипт проб](../tools/probe_derive_python.py) запускает cjc отдельно для каждого
случая, сохраняет исходник, `.macrocall`, диагностики и `results.json` в новом
каталоге. Это compile-only аудит; он не подтверждает работу Python, ABI,
управление ссылками или готовность к MCP.

| Проба | Результат среза |
|---|---|
| `primitive_control` | exit 0: обычное преобразование String → PyObj доступно извне |
| `scalar`, `default_arg` | exit 1: недоступный constructor PyObj; default дополнительно проверен по expansion |
| `record` | exit 1: непубличные типы runtime и последующие ошибки generated code |
| `external_extend` | exit 1: отсутствует `Existing__PyInteropNativeDescriptor` |
| `callback` | exit 1: отсутствует подходящее `FromPy` для функционального типа, также G0 |
| `generic` | exit 1: неизвестный T / generic type без аргументов, также G0 |
| `enum_pair` | exit 1: ASTException в `makeFakeClass`, до проверки типов |
| `enum_result` | exit 1: G0; enum conversions остаются отдельным выводом по исходникам, эта проба не изолирует G3 |
| `private_ctor` | exit 1: нет конструктора Hidden(), также G0 |

Воспроизведение из cjmcp, с новыми каталогами:

```sh
git clone https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop.git /tmp/cjmcp-interop-check
git -C /tmp/cjmcp-interop-check checkout --detach c66c1825df7f8eff95244fce4cdc8f273a215dd7
(cd /tmp/cjmcp-interop-check && cjpm build)
python3 tools/probe_derive_python.py \
  --interop /tmp/cjmcp-interop-check/target/release/py_interop \
  --out /tmp/cjmcp-derive-check
```

При сверке учтены 137 деклараций типов/функций и две константы; два public re-export (`TextRange`, `TextEdit`) указаны отдельно.

Скрипт возвращает ненулевой статус, если не компилируется контрольная проба;
остальные отказы записывает как результаты аудита. Переход на новую версию
interop требует повторного анализа, а не механической замены ожидаемых exit codes.

Предлагаемая последовательность реализации:

1. **G0, G9, G10 и минимальный запуск.** Выбрать и проверить схему
   «Cangjie host + embedded Python» либо отдельный CPython extension bootstrap.
   Успешно вызвать из Python функцию String → String и получить простой DTO.
   Проверить неверный тип аргумента, отсутствующий аргумент и CJ exception.
   Для runtime-сборки согласовать CPython headers/ABI с `build/build.py`,
   библиотеку Python и SDK; build-only пробы этого не делают.
2. **Один владелец workspace.** Concrete facade владеет VFS, project model и root
   database; read-запрос берёт snapshot. На внешней границе — пути, текст,
   UTF-8 byte offsets и DTO диапазонов. Если нужен line/column, кодировка задаётся
   явно; Python character index не равен byte offset.
3. **Первый сквозной сценарий.** Загрузить проект/SDK, добавить или изменить файл,
   вызвать `diagnostics`, `hoverAt`, `definitionAt`, затем повторить после изменения.
   Проверить кириллицу/emoji, отмену и удаление. Связать результаты с путями;
   сохранить диагностические диапазоны, severity и `None` без потери смысла.
4. **Остальные независимые запросы.** Символы, ссылки, реализации, структура,
   форматирование, folding, selection, highlighting. Возвращать immutable DTO;
   enum пока переводить в теги, defaults задавать в фасаде.
5. **Completion и expansion.** Добавить токены с владельцем и ревизией,
   отклонение устаревших токенов, ограничение их количества/времени жизни и
   освобождение snapshot. Для расширений обеспечить входные macro outputs;
   `expandedMacro` сам не заменяет работу macro server.
6. **Расширять генератор по потребности.** G2/G3 полезны многим DTO; G1 имеет
   смысл при намерении предоставить исходные типы как самостоятельную Python
   библиотеку. G5/G6 не нужны для первых MCP tools при описанной границе.

Граница Python bindings и JSON-схема MCP — разные контракты: proxy-объект
сам по себе не JSON. Преобразование DTO в MCP response и нормализация ошибок
должны быть явными. До окончания первого сквозного сценария не стоит строить
реализацию на предположении, что blanket `@DerivePython` экспортирует loupe.

[loupe-manifest]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/cjpm.toml
[project-manifest]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/project_model/cjpm.toml
[loupe-src]: https://github.com/ide4cj/cjls/tree/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src
[project-src]: https://github.com/ide4cj/cjls/tree/371069c9312b8ddb4cc5045349937235218693f8/modules/project_model/src
[database]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/db/db.cj
[db-project]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/db/project.cj
[macro-output]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/db/macro_output.cj
[vfs]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/vfs.cj
[paths]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/path.cj
[loader]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/modules/loupe/src/vfs/loader.cj
[analysis-rules]: https://github.com/ide4cj/cjls/blob/371069c9312b8ddb4cc5045349937235218693f8/docs/design/02-analysis.md
[generator]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/c66c1825df7f8eff95244fce4cdc8f273a215dd7/src/internal_macros/c_enable.cj
[converters]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/c66c1825df7f8eff95244fce4cdc8f273a215dd7/src/cjobj.cj
[proxy]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/c66c1825df7f8eff95244fce4cdc8f273a215dd7/src/pyproxy.cj
[pyobj]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/c66c1825df7f8eff95244fce4cdc8f273a215dd7/src/pyobj.cj
[example]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/c66c1825df7f8eff95244fce4cdc8f273a215dd7/examples/example.cj
[interop-build]: https://gitcode.com/belyaev-mikhail/cangjie_python_reverse_interop/blob/c66c1825df7f8eff95244fce4cdc8f273a215dd7/build/build.py
