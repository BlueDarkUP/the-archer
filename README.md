# The Archer | 实时弹道解算与可视化工具

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Framework: Tkinter](https://img.shields.io/badge/Framework-Tkinter-orange.svg)](https://docs.python.org/3/library/tkinter.html)

一款为机器人竞赛设计的交互式2D场地模拟器，能够实时计算并可视化考虑了空气阻力和载具运动的发射方案。


## 简介

在机器人射击类竞赛中，精确的瞄准至关重要。当机器人自身在移动时，计算发射角度、速度和方位角会变得异常复杂。"The Archer" 通过一个直观的图形化界面解决了这个问题。用户可以在模拟场地上拖动机器人位置、设定其运动速度和方向，程序会通过后台线程实时解算出最优的发射方案，并将弹道轨迹清晰地绘制出来。

这个工具旨在帮助：
*   **软件团队**：验证和调试瞄准算法，理解运动补偿的原理。
*   **策略分析**：快速评估在场上不同位置射击的可行性与难度。
*   **物理学习**：直观地观察空气阻力等因素对抛体运动的影响。

## 主要功能

*   **交互式场地视图**：通过鼠标在 1:1 缩放的场地上拖动机器人，实时更新坐标。
*   **实时弹道解算**：在后台线程中进行高频计算，不阻塞UI，实现流畅的实时反馈。
*   **完整的物理模型**：仿真计算中包含了**重力**和**空气阻力**，使结果更贴近真实世界。
*   **运动补偿计算**：支持输入机器人自身的线速度和方向，程序会自动计算出为了命中静止目标，发射器需要瞄准的提前量（方位角）和调整后的发射速度。
*   **数据可视化**：
    *   在场地视图中清晰地展示目标连线、机器人运动矢量和发射器瞄准方向。
    *   在右侧面板中实时绘制精确的弹道轨迹图。
*   **参数化显示**：清晰地展示坐标、距离、目标角度、以及最终解算出的发射俯仰角、方位角和速度。
*   **联盟切换**：支持红蓝双联盟目标点的选择。

## 技术实现

*   **前端界面**：使用 Python 内置的 `Tkinter` 库构建，并借助 `Matplotlib` 实现动态的轨迹绘图。
*   **物理仿真**：采用**欧拉法（Euler's method）**进行数值积分，以微小的时间步长（`TIME_STEP_S`）迭代模拟投射物在重力和空气阻力共同作用下的运动过程。
*   **寻优算法**：为了找到最优解（通常是能量最小的解），采用了一种多阶段的搜索策略：
    1.  **解析估算**：首先使用无空气阻力的理想抛体运动公式，估算出一个初始速度作为搜索起点。
    2.  **线性搜索**：从估算点开始，以固定步长增加速度，快速找到一个能击中目标高度上下的速度区间。
    3.  **二分搜索**：在确定的区间内，使用二分法（Bisection method）进行多次迭代，以高精度收敛到最终的发射速度。
*   **多线程UI**：为了防止复杂的物理计算导致界面卡顿，程序将计算任务置于一个独立的**后台工作线程**。主UI线程通过 `queue` 模块与工作线程安全地通信，将计算参数传递给后者，并异步获取计算结果来更新界面。
*   **矢量补偿**：机器人的运动补偿通过矢量运算实现。最终投射物的速度矢量 (`V_projectile`) 是机器人速度矢量 (`V_vehicle`) 和发射器射出速度矢量 (`V_launcher`) 的和。程序通过反向计算 `V_launcher = V_projectile - V_vehicle` 来求解发射器所需的速度和方向。

## 安装与运行

### 环境要求
*   Python 3.9 或更高版本
*   `pip` 包管理器

### 安装步骤

1.  **克隆仓库**
    ```bash
    git clone https://github.com/BlueDarkUP/the-archer.git
    cd the-archer
    ```

2.  **安装依赖库**
    项目依赖于 `Numpy`, `Matplotlib` 和 `Pillow`。建议创建一个 `requirements.txt` 文件来管理它们。

    **requirements.txt:**
    ```
    numpy
    matplotlib
    Pillow
    ```

    然后通过 pip 安装：
    ```bash
    pip install -r requirements.txt
    ```

3.  **准备背景图片**
    程序会尝试加载名为 `ttt.jpg` 的场地背景图片。请确保该图片与主程序文件在同一目录下。如果找不到该图片，程序会以纯白背景运行。

4.  **运行程序**
    假设您的主文件名为 `main.py`：
    ```bash
    python main.py
    ```

## 使用指南

1.  运行程序后，您会看到一个包含场地和控制面板的窗口。
2.  在左侧的场地区域，用鼠标**左键点击并拖动**黑色的圆点，这代表您的机器人。
3.  在右侧的控制面板中：
    *   **Target Alliance**: 选择您要瞄准的目标（红色或蓝色）。
    *   **Position & Distance**: 查看机器人的精确坐标、到目标的距离和角度。
    *   **Vehicle Motion**: 拖动滑块来设置机器人当前的速度和运动方向。橙色箭头会出现在场地上，直观表示机器人的运动状态。
    *   **Launch Solution**: 实时查看程序计算出的发射方案，包括发射俯仰角、方位角和速度。灰色虚线箭头表示发射器的瞄准方向。
4.  右下角的图表会实时显示当前方案下的弹道轨迹。

## 开源许可

本项目采用 [MIT License](./LICENSE) 开源。

<details>
<summary>MIT License 详情</summary>

```
MIT License

Copyright (c) 2025 [Your Name or Organization]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```</details>

## 如何贡献

欢迎任何形式的贡献！如果您有任何建议、发现bug或想要添加新功能，请随时：
*   提交一个 [Issue](https://github.com/your_username/the-archer/issues)
*   Fork 本项目并提交一个 Pull Request

## 致谢

*   **程序开发**: BlueDarkUP