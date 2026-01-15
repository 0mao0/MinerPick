# MinerPick ⚒️

[English](#english) | [中文](#chinese)

---
<p align="center">
  <img src="docs/images/product_view.png" width="500px" />
</p>

<a name="english"></a>
## English

**One-liner**: A full-stack PDF ↔ Markdown “mirror” with pixel-level highlighting and editable table cells, designed for LLM workflows.

### 🛠️ Architecture

#### 1) Data Pipeline (Backend)
- **PDF Upload**: `main.py` -> `input/`
- **Parsing**: `MinerUParser` (API) -> `content.md` + `content_list.json`- **Table Enrichment**: `GMFTTableExtractor` (`gmft`) -> `content_tables.json` (Cell-level coords)
- **Mapping**: `_build_md_first_content_list` maps MD blocks to PDF bboxes.

<p align="center">
  <img src="docs/images/backend_flow.png" width="500px" />
</p>

#### 2) Interaction Flow (Frontend)
- **Rendering**: `MarkdownViewer.vue` (MD) + `PdfViewer.vue` (PDF)
- **Sync**: Hover/Click index -> Lookup JSON -> Emit coordinates -> Render Highlight box.

<p align="center">
  <img src="docs/images/frontend_sync.png" width="500px" />
</p>

### 🆚 Comparison (vs. similar products)

The table below compares MinerPick with other major open-source or commercial products.

| Dimension | MinerPick (Target) | MinerU (Magic-PDF) | Marker | Docling | Unstructured / LlamaParse |
|---|---|---|---|---|---|
| **Layout Restoration** | ✅ **High** <br>*(Visual + Structural)* | ✅ **High** <br>*(Structural)* | ✅ **High** <br>*(Structural)* | ✅ **High** <br>*(Structural)* | ❌ **Low** <br>*(Chunk-first)* |
| **Sync Highlighting** | ✅ **Full-stack** <br>*(Ready-to-use UI)* | ⚠️ **Raw Data** <br>*(JSON Bbox available)* | ❌ **None** <br>*(Text-only)* | ⚠️ **Raw Data** <br>*(Granular Bbox)* | ⚠️ **Block-level** <br>*(Element Bbox)* |
| **Table Coordinates** | ✅ **Cell-level** <br>*(Exact Bbox)* | ⚠️ **Structure** <br>*(HTML/MD Block)* | ❌ **Text-only** <br>*(MD Table)* | ⚠️ **Structure** <br>*(Parsed HTML)* | ⚠️ **Block-level** <br>*(Table Region)* |
| **Editable Mapping** | ✅ **Native** <br>*(Keep bbox)* | ❌ **No** | ❌ **No** | ❌ **No** | ❌ **No** |
| **Self-Hostable** | ✅ **Yes** | ✅ **Yes** | ✅ **Yes** | ✅ **Yes** | ⚠️ **Partial** <br>*(Limited/OSS)* |
| **API Interface** | ✅ **FastAPI** <br>*(HTTP Service)* | ⚠️ **CLI/SDK** <br>*(Python Lib)* | ❌ **Script** <br>*(Local Tool)* | ⚠️ **Python Lib** <br>*(Local SDK)* | ✅ **API-First** <br>*(Cloud/SaaS)* |

### 🧪 Cases (Coming soon)

- Case studies: **TBD (to be published)**.

### 🌐 Online Demo

- Online demo: **http://124.221.238.70:8005/**.

### ▶️ Usage

#### 1) Prerequisites
- Python 3.10+
- Node.js 18+

#### 2) Backend
```bash
pip install -r requirements.txt
cp .env.example .env
python backend/main.py
```

#### 3) Frontend
```bash
cd frontend
npm install
npm run dev
```

#### Notes
- Built on MinerU and gmft.

---

<a name="chinese"></a>
## 中文



**一句话描述**：面向 LLM 的全栈 PDF ↔ Markdown “镜像”工具，支持像素级高亮对齐与表格单元格编辑。

### 🛠️ 技术架构

#### 1) 数据处理流程 (后端)
- **PDF 上传**: `main.py` -> 存储至 `input/`
- **内容解析**: `MinerUParser` (调用 API) -> 生成 `content.md` + `content_list.json`
- **表格增强**: `GMFTTableExtractor` (`gmft`) -> 提取单元格级坐标 `content_tables.json`
- **对齐映射**: `_build_md_first_content_list` 算法将 MD 区块与 PDF 坐标进行关联。

#### 2) 同步高亮交互 (前端)
- **双端渲染**: `MarkdownViewer.vue` (渲染 MD) + `PdfViewer.vue` (渲染 PDF)
- **交互对齐**: 悬停/点击索引 -> 查询 JSON 映射 -> 发送坐标 -> 在 PDF 上层绘制高亮框。

<p align="center">
  <img src="docs/images/fullstack_framework.png" width="400px" />
</p>


### 🆚 同类产品对比

下表将 MinerPick 与市场其他主流开源或商业产品进行对比。

| 维度 | MinerPick (目标产品) | MinerU (Magic-PDF) | Marker | Docling | Unstructured / LlamaParse |
|---|---|---|---|---|---|
| **版面还原能力** | ✅ **高** <br>*(视觉 + 结构)* | ✅ **高** <br>*(结构级)* | ✅ **高** <br>*(结构级)* | ✅ **高** <br>*(结构级)* | ❌ **低** <br>*(分块优先)* |
| **同步高亮** | ✅ **全栈支持** <br>*(开箱即用 UI)* | ⚠️ **原始数据** <br>*(含 JSON 坐标)* | ❌ **无** <br>*(纯文本)* | ⚠️ **原始数据** <br>*(细粒度坐标)* | ⚠️ **块级** <br>*(元素坐标)* |
| **表格坐标** | ✅ **单元格级** <br>*(精确 Bbox)* | ⚠️ **结构级** <br>*(HTML/MD 块)* | ❌ **纯文本** <br>*(MD 表格)* | ⚠️ **结构级** <br>*(解析后的 HTML)* | ⚠️ **块级** <br>*(表格区域)* |
| **可编辑映射** | ✅ **原生支持** <br>*(保留 Bbox)* | ❌ **不支持** | ❌ **不支持** | ❌ **不支持** | ❌ **不支持** |
| **本地化部署** | ✅ **支持** | ✅ **支持** | ✅ **支持** | ✅ **支持** | ⚠️ **部分支持** <br>*(有限/开源版)* |
| **API 优先架构** | ✅ **FastAPI** <br>*(HTTP 服务)* | ⚠️ **CLI/SDK** <br>*(Python 库)* | ❌ **脚本** <br>*(本地工具)* | ⚠️ **Python 库** <br>*(本地 SDK)* | ✅ **API 优先** <br>*(云服务/SaaS)* |


### 🧪 案例（待发布）

- 案例集：**待发布**。

### 🌐 在线体验地址

- 在线体验：**http://124.221.238.70:8005/**。

### ▶️ 使用方法

#### 1）环境要求
- Python 3.10+
- Node.js 18+

#### 2）启动后端
```bash
pip install -r requirements.txt
cp .env.example .env
python backend/main.py
```

#### 3）启动前端
```bash
cd frontend
npm install
npm run dev
```

#### 说明
- 本项目基于 MinerU 和 gmft 开发。

### 📄 License

MIT License. See [LICENSE](LICENSE).
