# SrcGraph (SourceGraph)

[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/yourusername/SrcGraph)
[![Python](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**SrcGraph** is an experimental node-graph based tool built with Python 3.14 and PySide6 (Qt). It is designed to provide a flexible and extensible environment for visual logic orchestration, with a particular focus on Source Engine (QC) model processing and general-purpose primitive operations.

## ⚠️ Alpha Warning

**This project is currently in Alpha.**
- **Note:** Only a small subset of QC (Source Engine) commands are currently implemented. For practical Source Engine model projects, the current utility is near zero as most essential commands are missing.
- Nothing is guaranteed to work as expected.
- The system architecture, file formats, and node logic will change frequently and significantly.
- Expect bugs, crashes, and breaking changes.
- Use at your own risk.

## Features

- **Visual Node Editor:** A flexible graph-based interface for connecting logic.
- **Extensible Node System:** 
  - **Primitive Nodes:** Basic data types, converters, and control flow.
  - **QC Nodes:** Specialized nodes for Source Engine model definitions (QC), animations, and rendermesh settings.
  - **Subgraphs:** Create reusable node groups within larger graphs.
- **Real-time Execution:** Execute graphs with a dedicated engine and context management.
- **Rich GUI:** Includes an Inspector, History (Undo/Redo), Graph Map, Console, and specialized browsers for variables and assets.
- **Undo/Redo Support:** Integrated undo manager for all graph operations.
- **Inspirations:** Many features are inspired by Valve's Source2 Animgraph node tool and popular node-based interfaces like ComfyUI (LiteGraph).

## Requirements

- **Python 3.14+**
- **Dependencies:**
  - `PySide6`
  - `moderngl`
  - `numpy`

## Getting Started

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/SrcGraph.git
   cd SrcGraph
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python main.py
   ```

## Development

The project is structured into several core modules:
- `core/`: Graph logic, node definitions, and execution engines.
- `gui/`: UI components, panels, and custom widgets.
- `nodes/`: Implementation of various node categories.
- `workspace/`: Default workspace configurations.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
