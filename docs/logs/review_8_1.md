你是一名资深开发人员， 目前 docs/plan/python-core-port-plan.md 第8层的第一条的需求 被 分解为 docs/plan/phase_8_1.md 然后实现了一下 ， 你评审一下。


 ### P1 - High

  1. Returned and persisted graphs can contain dangling call edges
     src/understand_anything/pipeline.py:261, src/understand_anything/pipeline.py:445

     Pipeline.run() calls validate_graph(...), but it keeps returning and persisting the original graph, not validation.data. At the
     same time _resolve_and_add_calls() blindly adds every extracted call edge as if the callee were in the same file:

     builder.add_call_edge(
         caller_file=rel_path,
         caller_func=entry.caller,
         callee_file=rel_path,
         callee_func=entry.callee,
     )

     This creates invalid graph edges for external/library calls and cross-file calls. I reproduced this with a tiny TS project:

     dangling [('function:src/index.ts:main', 'function:src/index.ts:console.log', 'calls'),
               ('function:src/index.ts:main', 'function:src/index.ts:greet', 'calls')]
     validation True ['edges[1]: target "function:src/index.ts:console.log" does not exist in nodes — removed',
                      'edges[2]: target "function:src/index.ts:greet" does not exist in nodes — removed']

     The validator detects and removes these edges in its sanitized output, but the pipeline discards that sanitized output.
     Consumers of result.graph and the raw persisted knowledge-graph.json can therefore see invalid edge references even when
     result.validation.success is True.

     Suggested fix: either only add call edges after checking that both endpoint node IDs exist, or replace the graph after
     validation with KnowledgeGraph.model_validate(validation.data) when validation succeeds. For call graph resolution, cross-file
     symbol calls need actual import/specifier resolution; otherwise skip unresolved callees instead of fabricating same-file
     targets.

  2. Detected layers and tour are not written back to the graph or persisted
     src/understand_anything/pipeline.py:270, src/understand_anything/pipeline.py:280, src/understand_anything/pipeline.py:291

     detect_layers(graph) and generate_heuristic_tour(...) populate local variables, but the original graph.layers and graph.tour
     remain empty. Persistence then saves the original graph:

     graph_with_layers = graph.model_copy(deep=True)
     graph_with_layers.layers = layers
     tour = generate_heuristic_tour(graph_with_layers)
     ...
     save_graph(self._project_root, graph)

     Reproduction output:

     len(result.layers)=1
     len(result.tour)=2
     len(result.graph.layers)=0
     len(result.graph.tour)=0
     len(saved.layers)=0
     len(saved.tour)=0

     This misses a core part of docs/plan/phase_8_1.md: the pipeline is supposed to run layer detection, tour generation, then
     persist the graph/meta/fingerprints. The persisted graph currently loses the generated architecture/tour data.

     Suggested fix: construct a final_graph = graph.model_copy(deep=True), assign final_graph.layers = layers and final_graph.tour =
     tour, validate/persist/return that final graph consistently.

  ### P2 - Medium

  3. Import edge creation is file-order dependent
     src/understand_anything/pipeline.py:192, src/understand_anything/pipeline.py:220, src/understand_anything/pipeline.py:453

     Import resolution only matches against analyzed_paths, which is populated incrementally during the same loop. If an importer is
     processed before its target file, the import edge is silently skipped. I reproduced this by forcing _discover_files() to return
     index.ts before utils.ts; the resulting imports edge list was empty:

     []

     This directly affects the TypeScript requirement in phase_8_1.md that ./utils imports resolve correctly. The current passing
     test depends on the local Path.rglob()/filesystem order returning utils.ts before index.ts; that order is not a reliable
     contract.

     There is also a path normalization issue at src/understand_anything/pipeline.py:498: Path(resolved).resolve() resolves relative
     to the process working directory, not project_root. The fallback often saves the common case, but the implementation is still
     conceptually wrong.

     Suggested fix: use a two-pass pipeline. First analyze all readable files and build the complete set of analyzed paths/nodes.
     Then resolve imports against that complete set. For relative import normalization, resolve via (self._project_root /
     Path(rel_path).parent / source).resolve().

  4. Integration tests are too permissive and miss the main regressions above
     tests/test_integration/test_complete_pipeline.py:96, tests/test_integration/test_complete_pipeline.py:199

     The TypeScript test only asserts len(import_edges) >= 1, not the exact file:src/index.ts -> file:src/utils.ts edge. It also
     does not vary file discovery order. The persistence test checks node counts only, so it misses that layers and tour are not
     saved. No test asserts that every edge source/target exists in graph.nodes.

     Suggested additions:

     node_ids = {n.id for n in result.graph.nodes}
     assert all(e.source in node_ids and e.target in node_ids for e in result.graph.edges)

     Also assert exact import edge endpoints, force importer-before-importee ordering in one test, and verify
     load_graph(...).layers / load_graph(...).tour are non-empty when those stages are enabled.

  ### P3 - Low

  5. Unused test import
     tests/test_integration/test_complete_pipeline.py:11

     pytest is imported but unused. Ruff did not flag it with current configuration, so this is non-blocking, but it should be
     removed.


你来修复一下， 我想保留箭头函数或嵌套函数 call 边，让结构提取/GraphBuilder 为这些 caller 创建稳定节点， 然后  _resolve_and_add_calls() 同时验证 caller 和 callee

这个会影响到 c/c++  和  java/kotlin 么？

会有影响，但影响范围分语言：

  C/C++：会受益，主要是更安全地过滤 call 边

  当前 C/C++ 是支持的。证据是 src/understand_anything/plugins/tree_sitter.py:96 的内置注册包含：

  ExtractorRegistration(language_id="cpp", extractor=CppExtractor()),
  ExtractorRegistration(language_id="c", extractor=CppExtractor()),

  C/C++ 的结构提取会把函数定义加入 analysis.functions，证据在 src/understand_anything/plugins/extractors/cpp.py:478。类/struct 内联
  方法也会加入 functions，同时加入 ClassInfo.methods，证据在 src/understand_anything/plugins/extractors/cpp.py:390 和 src/
  understand_anything/plugins/extractors/cpp.py:413。

  所以这次 _resolve_and_add_calls() 同时校验 caller/callee 后，对 C/C++ 的效果是：

  - main -> helper 这种同文件、两端都有节点的 call 边会保留。
  - obj.method() 这类如果 callee 能归一化成已知方法名，会保留。
  - 外部函数、库函数、无法对应到本文件节点的调用会被跳过，避免 enable_validation=False 时写出 dangling edge。
  - 对 qualified call 有一个现有限制：CppExtractor._extract_callee_name() 对 ns::foo() 可能返回完整 qualified text，证据在 src/
    understand_anything/plugins/extractors/cpp.py:523。当前 _normalize_call_name() 只处理 .，不处理 ::。因此 ns::foo -> foo 这种归一
    化当前版本不支持；结果会是保守跳过，不会生成悬空边。

  Java：会受益，也会更保守地过滤外部/构造调用

  Java 当前也是支持的。证据是 src/understand_anything/plugins/tree_sitter.py:103：

  ExtractorRegistration(language_id="java", extractor=JavaExtractor()),

  Java 的结构提取会把 method 和 constructor 都加入 functions，证据在 src/understand_anything/plugins/extractors/java.py:399 和 src/
  understand_anything/plugins/extractors/java.py:437。call graph 的 caller 也来自 method/constructor，证据在 src/
  understand_anything/plugins/extractors/java.py:153。

  所以 Java 路径基本符合这次修复的假设：caller 通常有稳定 function:{file}:{method} 节点。

  影响：

  - run -> helper 这种同类/同文件方法调用会保留。
  - System.out.println(...) 会被过滤，因为它不是本文件已知函数/方法。这是期望的，避免外部调用形成悬空边。
  - new Bar() 当前 Java extractor 会产出 callee "new Bar"，证据在 src/understand_anything/plugins/extractors/java.py:174。
    _normalize_call_name() 不会把 "new Bar" 归一化成 "Bar"，所以即使同文件有 Bar 构造函数节点，这条 call 边也会被跳过。换句话说：更
    安全，但对象创建边会少一些。如果后续想保留 new Bar -> Bar，需要专门加构造调用归一化规则。

  Kotlin：当前版本不支持，所以不会受影响

  本地代码没有 Kotlin extractor 注册。TreeSitterPlugin 的内置支持列表只注册了 TypeScript/TSX/JavaScript/Python/C++/C/Java，见 src/
  understand_anything/plugins/tree_sitter.py:96。

  虽然语言配置里有 Kotlin，例如 src/understand_anything/languages/configs/kotlin.py:10，但这只是语言配置，不等于 TreeSitter 结构提取
  支持。测试也明确把未支持语言排除在 SUPPORTED_TREE_SITTER_LANGUAGES 外，见 tests/test_plugins/test_tree_sitter.py:118。

  所以按项目规则“未知即不支持”：当前版本没有 Kotlin 结构提取/call graph 支持，这次修复不会影响 Kotlin。

  一句话结论

  - C/C++：会影响，主要是避免悬空 call 边；部分 qualified/外部调用会被保守跳过。
  - Java：会影响，方法调用更安全；外部调用和 new Bar 这类对象创建边当前会被跳过。
  - Kotlin：当前版本不支持 Kotlin extractor/call graph，所以无影响。
