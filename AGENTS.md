# test-deepseek-understand-anythin-port-python

## Quick Reference 
**Package Manager**: `uv`

## 核心行为准则

1. **禁止推测功能**：严禁根据通用编程经验推测项目支持的功能。所有功能支持情况必须以项目文档（docs/）或现有代码实现为准。
2. **未知即不支持**：如果文档或代码中没有明确找到某个功能的实现或说明，必须明确告知用户“当前版本不支持此功能”。
3. **引用来源**：在回答功能支持性问题时，必须引用具体的文档段落或代码文件路径作为证据。如果没有证据，则视为不支持。
4. **优先权**：项目本地文档的优先级高于你的内部训练知识。如果两者冲突，以本地文档为准。
5. **验证先于断言**：声称"完成"、"修复"、"通过"之前，必须运行验证命令并展示输出证据。禁止使用"应该能工作"、"看起来正确"等未经验证的断言。（详见 `.claude/rules/verification.md` 和 `/preprocessor_verification-before-completion` skill）
6. **必须尽力保证这四条检查命令都通过, 禁止通过添加 exclude 的方式来逃避检查, 功能正确优先于类型检查**
   + `uv run ruff check src`
   + `uv run ty check src`
   + `uv run mypy src`
   + `uv run pytest`


## 1.  Architecture Overview (The Big Picture)
本项目是一个高性能、AI 预处理问题 , 两种工作方式任选一种
1. 命令行方式(方便调试)。
2. 源头 understand-anything 的 Claude Code Plugin 方式

### Core Components Map
目录结构
```
```
+ **配置**: `src/understand_anything/config.py` 

## 约束
+ cli 胶水层在 src/understand_anything/cli 目录
   - 命令行实现用 click 库
   - 每个 top-level command 一个独立文件
   - 类似 `/home/an/workspace/python/meltano/src/meltano/cli` 这种处理方式
