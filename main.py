"""
    注释由 Gemini 2.5 Pro 提供
"""

import tkinter as tk
from tkinter import font as tkFont
import numpy as np
import math
import threading
import queue

from PIL import Image, ImageTk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- 常量定义 ---

# --- 场地常量 (单位: 英寸) ---
REAL_FIELD_SIZE = 141.170031  # 场地的实际尺寸 (宽度/高度)
REAL_PANEL_LENGTH = 27.889412  # 场地角落斜板的实际长度
FIELD_SIZE = 1.0  # 标准化场地尺寸，用于内部计算
NORMALIZED_PANEL_LENGTH = REAL_PANEL_LENGTH / REAL_FIELD_SIZE  # 标准化斜板长度
ANGLE_WITH_SIDE_WALL_DEG = 54.046000  # 斜板与侧墙的夹角 (度)

# --- UI 界面常量 ---
CANVAS_SIZE_PX = 1000  # 场地画布的像素尺寸 (正方形)
RIGHT_PANEL_WIDTH = 570  # 右侧控制面板的宽度 (像素)
PADDING_PX = 20  # 画布内边距 (像素)
INCHES_TO_METERS = 0.0254  # 英寸到米的转换系数

# --- 物理常量 ---
GRAVITY_MS2 = 9.81  # 重力加速度 (m/s^2)
AIR_DENSITY = 1.225  # 空气密度 (kg/m^3)
HEIGHT_M = 1.065  # 目标高度 (米)
MASS_KG = 0.012  # 投射物质量 (千克)
DRAG_COEFFICIENT = 0.25  # 投射物风阻系数
CROSS_SECTIONAL_AREA_M2 = 0.00928  # 投射物横截面积 (m^2)

# --- 计算参数 ---
MIN_ANGLE_DEG = 55.0  # 搜索的最小发射角度 (度)
MAX_ANGLE_DEG = 90.0  # 搜索的最大发射角度 (度)
THRESHOLD_DISTANCE_M = 0  # 决定搜索方向的距离阈值 (米)，此处未使用
ANGLE_SEARCH_STEP = 1.0  # 角度搜索步长 (度)
VELOCITY_SEARCH_STEP = 0.1  # 速度线性搜索步长 (m/s)
MAX_VELOCITY_TRIES = 500  # 速度线性搜索的最大尝试次数
BISECTION_ITERATIONS = 8  # 二分法迭代次数，用于精确查找速度
HIT_TOLERANCE_M = 0.055  # 命中目标高度的容差 (米)
TIME_STEP_S = 0.006  # 物理仿真的时间步长 (秒)


class FieldViewerApp:
    def __init__(self, root):
        self.root = root
        # 修改窗口标题
        self.root.title("The Archer | Powered by 27570")
        self.root.geometry("1920x1080")
        self.root.resizable(False, False)

        # 设置用于线程通信的队列
        self.calc_queue = queue.Queue(maxsize=1)  # 计算任务队列，最大容量为1，防止任务积压
        self.result_queue = queue.Queue()  # 计算结果队列

        # 创建并启动后台计算线程
        self.worker_thread = threading.Thread(target=self.calculation_worker, daemon=True)
        self.worker_thread.start()

        # 用于存储上一次的计算结果和参数
        self.last_solution = None
        self.last_calc_params = {}
        self.last_path = ([], [])

        # --- UI 布局 ---
        # 左侧画布框架
        canvas_frame = tk.Frame(root)
        canvas_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # 右侧控制面板框架
        right_panel = tk.Frame(root, width=RIGHT_PANEL_WIDTH)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=10)
        right_panel.pack_propagate(False)  # 防止框架自动缩放

        # 创建主画布
        self.canvas = tk.Canvas(canvas_frame, width=CANVAS_SIZE_PX, height=CANVAS_SIZE_PX, bg="white")
        self.canvas.pack()

        # 右侧面板中的控件框架
        self.controls_frame = tk.Frame(right_panel)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # 右侧面板底部的绘图框架
        plot_frame = tk.Frame(right_panel)
        plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        # 设置 Matplotlib 绘图区域
        self.fig = Figure(dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.plot_canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.plot_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- 字体定义 ---
        self.title_font = tkFont.Font(family="Arial", size=12, weight="bold")
        self.label_font = tkFont.Font(family="Consolas", size=10)
        self.bold_label_font = tkFont.Font(family="Consolas", size=11, weight="bold")
        self.credit_font = tkFont.Font(family="Arial", size=9, slant="italic")  # 为署名标签添加新字体

        # 初始化所有UI控件
        self.setup_controls()

        # --- 加载并处理背景图片 ---
        self.field_bg_image = None
        try:
            draw_size = CANVAS_SIZE_PX - 2 * PADDING_PX
            original_image = Image.open("ttt.jpg")
            image_with_alpha = original_image.convert("RGBA")
            pixel_data = image_with_alpha.getdata()
            new_pixel_data = []
            alpha_value = int(255 * (1.0 - 0.7))  # 设置70%的透明度
            for item in pixel_data:
                new_pixel_data.append((item[0], item[1], item[2], alpha_value))
            image_with_alpha.putdata(new_pixel_data)
            resized_image = image_with_alpha.resize((draw_size, draw_size), Image.Resampling.LANCZOS)
            self.field_bg_image = ImageTk.PhotoImage(resized_image)
        except FileNotFoundError:
            print("Warning: 'ttt.jpg' not found. Using a white background.")
        except Exception as e:
            print(f"Error loading background image: {e}")

        # 初始化拖拽点的位置 (标准化坐标)
        self.drag_pos_x, self.drag_pos_y = 0.5, 0.5
        # 计算场地的几何信息
        self.calculate_geometry()
        # 绘制静态的场地元素
        self.draw_static_field()
        # 绘制可交互的元素
        self.draw_interactive_elements()

        # 每隔30毫秒检查一次计算结果队列
        self.root.after(30, self.process_results)
        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.on_mouse_action)
        self.canvas.bind("<B1-Motion>", self.on_mouse_action)

    def setup_controls(self):
        # 设置控件框架的网格布局权重
        self.controls_frame.columnconfigure(0, weight=0)
        self.controls_frame.columnconfigure(1, weight=1)
        row_idx = 0  # 网格行索引

        # --- 目标联盟选择 ---
        tk.Label(self.controls_frame, text="Target Alliance", font=self.title_font).grid(row=row_idx, column=0,
                                                                                         columnspan=2, sticky='w',
                                                                                         pady=(0, 5))
        row_idx += 1
        self.alliance_var = tk.StringVar(value="Red")
        alliance_frame = tk.Frame(self.controls_frame)
        tk.Radiobutton(alliance_frame, text="Red Alliance (Right Tag)", variable=self.alliance_var, value="Red",
                       command=self.draw_interactive_elements).pack(side=tk.LEFT, padx=(0, 10))
        tk.Radiobutton(alliance_frame, text="Blue Alliance (Left Tag)", variable=self.alliance_var, value="Blue",
                       command=self.draw_interactive_elements).pack(side=tk.LEFT)
        alliance_frame.grid(row=row_idx, column=0, columnspan=2, sticky='w')
        row_idx += 1

        # 分割线
        tk.Frame(self.controls_frame, height=2, bg="lightgray").grid(row=row_idx, column=0, columnspan=2, sticky='ew',
                                                                     pady=10)
        row_idx += 1

        # --- 位置与距离信息 ---
        tk.Label(self.controls_frame, text="Position & Distance", font=self.title_font).grid(row=row_idx, column=0,
                                                                                             columnspan=2, sticky='w',
                                                                                             pady=(0, 5))
        row_idx += 1
        tk.Label(self.controls_frame, text="Coordinates:", font=self.bold_label_font).grid(row=row_idx, column=0,
                                                                                           sticky='w', padx=5)
        self.coord_label = tk.Label(self.controls_frame, text="X=0.500, Y=0.500", font=self.label_font)
        self.coord_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1
        tk.Label(self.controls_frame, text="Field Angle:", font=self.bold_label_font).grid(row=row_idx, column=0,
                                                                                           sticky='w', padx=5)
        self.angle_label = tk.Label(self.controls_frame, text="0.00 deg", font=self.label_font)
        self.angle_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1
        tk.Label(self.controls_frame, text="To Blue Tag:", font=self.bold_label_font, fg="blue").grid(row=row_idx,
                                                                                                      column=0,
                                                                                                      sticky='w',
                                                                                                      padx=5)
        self.dist_blue_label = tk.Label(self.controls_frame, text="--", font=self.label_font, fg="blue")
        self.dist_blue_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1
        tk.Label(self.controls_frame, text="To Red Tag:", font=self.bold_label_font, fg="red").grid(row=row_idx,
                                                                                                    column=0,
                                                                                                    sticky='w', padx=5)
        self.dist_red_label = tk.Label(self.controls_frame, text="0.00 in", font=self.label_font, fg="red")
        self.dist_red_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1

        # 分割线
        tk.Frame(self.controls_frame, height=2, bg="lightgray").grid(row=row_idx, column=0, columnspan=2, sticky='ew',
                                                                     pady=10)
        row_idx += 1

        # --- 机器人运动控制 ---
        tk.Label(self.controls_frame, text="Vehicle Motion", font=self.title_font).grid(row=row_idx, column=0,
                                                                                        columnspan=2, sticky='w',
                                                                                        pady=(0, 5))
        row_idx += 1
        self.vehicle_speed_ms = tk.DoubleVar(value=0.0)
        self.vehicle_direction_deg = tk.DoubleVar(value=0.0)
        tk.Label(self.controls_frame, text="Velocity (m/s):").grid(row=row_idx, column=0, sticky='w', padx=5, pady=2)
        tk.Scale(self.controls_frame, from_=0.0, to=5.0, resolution=0.1, orient=tk.HORIZONTAL,
                 variable=self.vehicle_speed_ms, command=self.on_motion_change).grid(row=row_idx, column=1, sticky='ew')
        row_idx += 1
        tk.Label(self.controls_frame, text="Direction (deg):").grid(row=row_idx, column=0, sticky='w', padx=5, pady=2)
        tk.Scale(self.controls_frame, from_=0, to=360, resolution=1, orient=tk.HORIZONTAL,
                 variable=self.vehicle_direction_deg, command=self.on_motion_change).grid(row=row_idx, column=1,
                                                                                          sticky='ew')
        row_idx += 1

        # 分割线
        tk.Frame(self.controls_frame, height=2, bg="lightgray").grid(row=row_idx, column=0, columnspan=2, sticky='ew',
                                                                     pady=10)
        row_idx += 1

        # --- 发射方案实时显示 ---
        tk.Label(self.controls_frame, text="Launch Solution (Real-time)", font=self.title_font).grid(row=row_idx,
                                                                                                     column=0,
                                                                                                     columnspan=2,
                                                                                                     sticky='w',
                                                                                                     pady=(0, 5))
        row_idx += 1
        self.draw_plot_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.controls_frame, text="Enable Real-time Trajectory Plot", variable=self.draw_plot_var,
                       command=self.on_toggle_plot).grid(row=row_idx, column=0, columnspan=2, sticky='w')
        row_idx += 1
        tk.Label(self.controls_frame, text="Launch Pitch:", font=self.bold_label_font).grid(row=row_idx, column=0,
                                                                                            sticky='w', padx=5)
        self.launch_angle_label = tk.Label(self.controls_frame, text="--", font=self.label_font)
        self.launch_angle_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1
        tk.Label(self.controls_frame, text="Launcher Azimuth:", font=self.bold_label_font, fg="purple").grid(
            row=row_idx, column=0, sticky='w', padx=5)
        self.aim_azimuth_label = tk.Label(self.controls_frame, text="--", font=self.label_font, fg="purple")
        self.aim_azimuth_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1
        tk.Label(self.controls_frame, text="Launch Velocity:", font=self.bold_label_font).grid(row=row_idx, column=0,
                                                                                               sticky='w', padx=5)
        self.launch_velocity_label = tk.Label(self.controls_frame, text="--", font=self.label_font)
        self.launch_velocity_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1

        # --- 程序员署名 ---
        tk.Label(self.controls_frame, text="").grid(row=row_idx, column=0)  # 增加一些间距
        row_idx += 1

        credit_label = tk.Label(self.controls_frame, text="Programmed by BlueDarkUP", font=self.credit_font, fg="gray")
        credit_label.grid(row=row_idx, column=0, columnspan=2, sticky='e', padx=5)

    def on_toggle_plot(self):
        # 当“启用实时绘图”复选框状态改变时调用，用最新的数据更新绘图
        self.update_plot(self.last_solution, self.last_calc_params.get('distance_m', 0), self.last_path)

    def on_motion_change(self, _=None):
        # 当机器人运动滑块（速度或方向）改变时调用，重新绘制交互元素
        self.draw_interactive_elements()

    def calculation_worker(self):
        # 后台计算线程的循环体
        while True:
            try:
                # 从计算队列中获取任务参数，如果队列为空则阻塞等待
                calc_params = self.calc_queue.get()
                # 执行核心的求解函数
                solution = self.find_launch_solution(calc_params)
                # 将参数和求解结果放入结果队列
                self.result_queue.put((calc_params, solution))
            except Exception as e:
                print(f"Error in calculation worker: {e}")

    def process_results(self):
        # UI主线程中定期调用的函数，用于处理计算结果
        latest_result = None
        # 循环清空结果队列，只处理最新的一个结果，以避免UI更新延迟
        while not self.result_queue.empty():
            try:
                latest_result = self.result_queue.get_nowait()
            except queue.Empty:
                break

        if latest_result:
            calc_params, solution = latest_result
            # 使用最新的结果更新UI显示
            self.update_solution_display(solution, calc_params)

        # 再次安排此函数在30毫秒后运行
        self.root.after(30, self.process_results)

    def update_solution_display(self, solution, calc_params):
        # 根据计算结果更新UI界面上的标签和绘图
        self.last_solution = solution
        self.last_calc_params = calc_params
        distance_m = calc_params.get('distance_m', 0)

        path = ([], [])
        if solution:
            # 如果找到了解，则更新发射角度、方位角和速度的标签
            self.launch_angle_label.config(text=f"{solution['launcher_angle']:.2f} deg")
            self.aim_azimuth_label.config(text=f"{solution['aim_azimuth_deg']:.2f} deg")
            self.launch_velocity_label.config(text=f"{solution['launcher_velocity']:.2f} m/s")

            # 再次运行仿真以获取完整的轨迹路径用于绘图
            _, _, path_x, path_y = self.run_simulation_for_angle_and_velocity(
                solution['projectile_vertical_angle'], solution['projectile_total_velocity'], distance_m,
                return_path=True
            )
            path = (path_x, path_y)
        else:
            # 如果无解，则显示 "N/A"
            self.launch_angle_label.config(text="N/A")
            self.aim_azimuth_label.config(text="N/A")
            self.launch_velocity_label.config(text="N/A")

        self.last_path = path
        # 重绘画布上的交互元素（如瞄准线）
        self.draw_interactive_elements()
        # 更新右侧的轨迹图
        self.update_plot(solution, distance_m, path)

    def on_mouse_action(self, event):
        # 鼠标点击或拖拽时的事件处理器
        # 将画布的像素坐标转换为标准化的场地坐标
        fx, fy = self.canvas_to_field(event.x, event.y)
        # 限制坐标在 [0, 1] 范围内
        self.drag_pos_x = max(0.0, min(1.0, fx))
        self.drag_pos_y = max(0.0, min(1.0, fy))
        # 重绘交互元素以反映新位置
        self.draw_interactive_elements()

    def draw_interactive_elements(self):
        # 绘制所有与用户交互相关的动态元素
        self.canvas.delete("interactive")  # 删除旧的交互元素
        point_px = self.field_to_canvas(self.drag_pos_x, self.drag_pos_y)
        current_point_norm = np.array([self.drag_pos_x, self.drag_pos_y])

        # 绘制紫色十字虚线
        self.canvas.create_line(self.field_to_canvas(self.drag_pos_x, 1.0), self.field_to_canvas(self.drag_pos_x, 0.0),
                                fill="purple", dash=(5, 5), width=2, tags="interactive")
        self.canvas.create_line(self.field_to_canvas(0.0, self.drag_pos_y), self.field_to_canvas(1.0, self.drag_pos_y),
                                fill="purple", dash=(5, 5), width=2, tags="interactive")

        # 绘制代表机器人的黑色圆点
        self.canvas.create_oval(point_px[0] - 8, point_px[1] - 8, point_px[0] + 8, point_px[1] + 8,
                                fill="black", outline="gray", width=2, tags="interactive")

        # 根据选择的联盟确定目标位置和连线颜色
        alliance = self.alliance_var.get()
        target_tag_pos, line_color = (self.tag_right, "red") if alliance == "Red" else (self.tag_left, "blue")
        vector_to_target = target_tag_pos - current_point_norm
        dist_norm = np.linalg.norm(vector_to_target)  # 计算标准化距离
        dist_in = dist_norm * REAL_FIELD_SIZE  # 转换为实际距离（英寸）

        # 更新UI上的距离标签
        if alliance == "Red":
            self.dist_red_label.config(text=f"{dist_in:.2f} in")
            self.dist_blue_label.config(text="--")
        else:
            self.dist_blue_label.config(text=f"{dist_in:.2f} in")
            self.dist_red_label.config(text="--")

        # 绘制从机器人到目标的连线
        self.canvas.create_line(point_px, self.field_to_canvas(*target_tag_pos), fill=line_color, width=3,
                                arrow=tk.LAST, tags="interactive")

        # 计算并更新UI上的角度和坐标标签
        angle_to_target_deg = math.degrees(math.atan2(vector_to_target[1], vector_to_target[0]))
        self.angle_label.config(text=f"{angle_to_target_deg:+.2f} deg")
        self.coord_label.config(text=f"X={self.drag_pos_x:.3f}, Y={self.drag_pos_y:.3f}")

        # 如果机器人有速度，则绘制代表其运动方向的橙色箭头
        vehicle_speed = self.vehicle_speed_ms.get()
        if vehicle_speed > 0.1:
            move_dir_rad = math.radians(self.vehicle_direction_deg.get())
            arrow_len_norm = vehicle_speed * 0.08  # 箭头长度与速度成正比
            end_norm_x = self.drag_pos_x + arrow_len_norm * math.cos(move_dir_rad)
            end_norm_y = self.drag_pos_y + arrow_len_norm * math.sin(move_dir_rad)
            self.canvas.create_line(point_px, self.field_to_canvas(end_norm_x, end_norm_y),
                                    arrow=tk.LAST, fill="orange", width=4, tags="interactive")

        # 如果有解，绘制代表发射器瞄准方向的灰色虚线箭头
        if self.last_solution:
            aim_azimuth_rad = math.radians(self.last_solution['aim_azimuth_deg'])
            heading_end_x = self.drag_pos_x + 1.5 * math.cos(aim_azimuth_rad)
            heading_end_y = self.drag_pos_y + 1.5 * math.sin(aim_azimuth_rad)
            self.canvas.create_line(point_px, self.field_to_canvas(heading_end_x, heading_end_y),
                                    arrow=tk.LAST, fill="#555555", width=5, dash=(6, 3), tags="interactive")

        # --- 触发后台计算 ---
        try:
            # 如果计算队列中有旧任务，先清空
            if not self.calc_queue.empty():
                self.calc_queue.get_nowait()

            # 准备新的计算参数
            calc_params = {
                'distance_m': dist_in * INCHES_TO_METERS,
                'vehicle_speed_ms': self.vehicle_speed_ms.get(),
                'vehicle_direction_deg': self.vehicle_direction_deg.get(),
                'target_direction_deg': angle_to_target_deg
            }
            # 将新任务放入队列
            self.calc_queue.put_nowait(calc_params)
        except queue.Full:
            pass  # 队列已满（理论上不会发生，因为我们先清空了）
        except queue.Empty:
            pass

    def field_to_canvas(self, x_norm, y_norm):
        # 将标准化的场地坐标 (0-1) 转换为画布的像素坐标
        draw_size = CANVAS_SIZE_PX - 2 * PADDING_PX
        # Y坐标需要翻转，因为场地坐标原点在左下，而画布坐标原点在左上
        return (PADDING_PX + x_norm * draw_size, (CANVAS_SIZE_PX - PADDING_PX) - y_norm * draw_size)

    def canvas_to_field(self, px, py):
        # 将画布的像素坐标转换为标准化的场地坐标 (0-1)
        draw_size = CANVAS_SIZE_PX - 2 * PADDING_PX
        # 同样需要翻转Y坐标
        return ((px - PADDING_PX) / draw_size, ((CANVAS_SIZE_PX - PADDING_PX) - py) / draw_size)

    def calculate_geometry(self):
        # 计算场地中目标点（Tag）的标准化坐标
        angle_rad = np.deg2rad(90.0 - ANGLE_WITH_SIDE_WALL_DEG)
        dx, dy = NORMALIZED_PANEL_LENGTH * np.cos(angle_rad), NORMALIZED_PANEL_LENGTH * np.sin(angle_rad)
        # 左上角目标
        self.p1_left, self.p2_left = np.array([dx, 1.0]), np.array([0.0, 1.0 - dy])
        self.tag_left = (self.p1_left + self.p2_left) / 2
        # 右上角目标
        self.p1_right, self.p2_right = np.array([1.0 - dx, 1.0]), np.array([1.0, 1.0 - dy])
        self.tag_right = (self.p1_right + self.p2_right) / 2

    def draw_static_field(self):
        # 绘制不随交互改变的静态场地元素
        # 绘制背景图片
        if self.field_bg_image:
            self.canvas.create_image(CANVAS_SIZE_PX / 2, CANVAS_SIZE_PX / 2,
                                     image=self.field_bg_image, anchor=tk.CENTER)

        # 绘制场地边框和坐标轴
        bl_px, tr_px = self.field_to_canvas(0, 0), self.field_to_canvas(1, 1)
        self.canvas.create_rectangle(bl_px[0], bl_px[1], tr_px[0], tr_px[1], outline="black", width=3)
        self.canvas.create_line(bl_px[0], bl_px[1], bl_px[0], tr_px[1], fill="gray", width=2, arrow=tk.LAST)
        self.canvas.create_text(bl_px[0] - 15, tr_px[1] + 10, text="Y", anchor="e", font=("Arial", 14, "bold"))
        self.canvas.create_line(bl_px[0], bl_px[1], tr_px[0], bl_px[1], fill="gray", width=2, arrow=tk.LAST)
        self.canvas.create_text(tr_px[0] - 10, bl_px[1] + 15, text="X", anchor="n", font=("Arial", 14, "bold"))
        self.canvas.create_text(bl_px[0] - 10, bl_px[1] + 10, text="(0,0)", anchor="ne")

        # 绘制代表目标的星星
        self.draw_star(*self.field_to_canvas(*self.tag_left), 10, "blue")
        self.draw_star(*self.field_to_canvas(*self.tag_right), 10, "red")

    def draw_star(self, cx, cy, size, color):
        # 辅助函数，用于在指定位置绘制一个五角星
        points = []
        for i in range(5):
            # 交替使用大半径和小半径来形成五角星的内外顶点
            for ang_mult in [i, i + 0.5]:
                ang = np.pi / 2 + ang_mult * 2 * np.pi / 5
                radius = size if ang_mult == i else size / 2
                points.extend([cx + radius * np.cos(ang), cy - radius * np.sin(ang)])
        self.canvas.create_polygon(points, fill=color, outline=color)

    def update_plot(self, solution, distance_m, path):
        # 更新右侧的 Matplotlib 轨迹图
        self.ax.clear()

        if not self.draw_plot_var.get():
            # 如果用户禁用了绘图
            self.ax.set_title("Trajectory Plotting Disabled")
            self.ax.text(0.5, 0.5, 'Plotting Disabled', ha='center', va='center', fontsize=12, color='gray',
                         transform=self.ax.transAxes)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        elif solution and path and path[0]:
            # 如果有解并且有轨迹数据
            path_x, path_y = path
            label_text = (
                f"Pitch: {solution['launcher_angle']:.1f}°, " f"Velocity: {solution['launcher_velocity']:.2f} m/s")
            self.ax.plot(path_x, path_y, 'g-', label=label_text)
            self.ax.plot(distance_m, HEIGHT_M, 'ro', markersize=8, label="Target")
            self.ax.grid(True)
            self.ax.set_title("Projectile Trajectory")
            self.ax.set_xlabel("Horizontal Distance (m)")
            self.ax.set_ylabel("Vertical Height (m)")
            self.ax.legend()
            self.ax.set_xlim(left=0)
            self.ax.set_ylim(bottom=0)
            self.ax.set_aspect('equal', adjustable='box')  # 保持宽高比
        else:
            # 如果无解
            self.ax.set_title("No Valid Solution Found")
            self.ax.grid(True)
            self.ax.set_xlim(left=0)
            self.ax.set_ylim(bottom=0)

        self.fig.tight_layout(pad=0.8)  # 调整布局防止标签重叠
        self.plot_canvas.draw()  # 刷新画布

    def run_simulation_for_angle_and_velocity(self, launch_angle_deg, initial_velocity_ms, distance_m,
                                              return_path=False):
        # 核心物理仿真函数，使用欧拉法进行数值积分
        angle_rad = math.radians(launch_angle_deg)
        vx, vy = initial_velocity_ms * math.cos(angle_rad), initial_velocity_ms * math.sin(angle_rad)
        x, y, current_time, prev_time = 0.0, 0.0, 0.0, 0.0
        path_x, path_y = ([0.0], [0.0]) if return_path else (None, None)

        # 预计算一些常量以提高效率
        drag_factor = 0.5 * AIR_DENSITY * DRAG_COEFFICIENT * CROSS_SECTIONAL_AREA_M2
        gravity_force_y = -MASS_KG * GRAVITY_MS2

        while True:
            # 仿真终止条件：水平速度为负（已回头）或在y<0时垂直速度也为负（已落地）
            if (vx <= 0 and x < distance_m) or (y < 0 and vy < 0):
                return (-1.0, -1.0, [], []) if return_path else (-1.0, -1.0)

            prev_x, prev_y, prev_time = x, y, current_time

            v_sq = vx ** 2 + vy ** 2
            if v_sq == 0:  # 避免除以零
                return (-1.0, -1.0, [], []) if return_path else (-1.0, -1.0)

            # 计算空气阻力
            v = math.sqrt(v_sq)
            drag = drag_factor * v_sq
            # 计算x和y方向的加速度（考虑重力和空气阻力）
            ax, ay = -drag * (vx / v) / MASS_KG, (gravity_force_y - drag * (vy / v)) / MASS_KG

            # 更新速度和位置
            vx += ax * TIME_STEP_S
            vy += ay * TIME_STEP_S
            x += vx * TIME_STEP_S
            y += vy * TIME_STEP_S
            current_time += TIME_STEP_S

            if return_path: path_x.append(x); path_y.append(y)

            # 检查是否越过目标水平距离
            if x >= distance_m:
                # 使用线性插值计算在目标水平距离处的精确高度和时间
                if (x - prev_x) == 0:
                    hit_h, hit_t = y, current_time
                else:
                    frac = (distance_m - prev_x) / (x - prev_x)
                    hit_h = prev_y + (y - prev_y) * frac
                    hit_t = prev_time + TIME_STEP_S * frac

                # 如果需要返回路径，修正最后一个点的位置
                if return_path:
                    path_x[-1], path_y[-1] = distance_m, hit_h
                    return hit_h, hit_t, path_x, path_y

                return hit_h, hit_t

    def estimate_initial_velocity(self, angle_deg, target_x, target_y):
        # 在不考虑空气阻力的情况下，估算能够击中目标的初始速度
        # 这是求解复杂问题的良好起点
        angle_rad = math.radians(angle_deg)
        cos_a, tan_a = math.cos(angle_rad), math.tan(angle_rad)
        denominator = 2 * (cos_a ** 2) * (target_x * tan_a - target_y)
        return math.sqrt((GRAVITY_MS2 * target_x ** 2) / denominator) if denominator > 0 else None

    def find_launch_solution(self, params):
        # 寻找最优发射方案的核心算法
        distance_m = params['distance_m']
        if distance_m <= 0: return None

        # 获取机器人自身运动参数
        v_vehicle_ms = params['vehicle_speed_ms']
        vehicle_dir_rad = math.radians(params['vehicle_direction_deg'])
        target_dir_rad = math.radians(params['target_direction_deg'])

        # 计算机器人速度矢量
        v_vehicle_vec = np.array([v_vehicle_ms * math.cos(vehicle_dir_rad),
                                  v_vehicle_ms * math.sin(vehicle_dir_rad)])

        min_v_sol, last_min_launcher_v = None, float('inf')

        # 根据距离决定角度搜索方向（从大到小或从小到大），这里简化为总是从小到大
        start, step, end_cond = (MIN_ANGLE_DEG, ANGLE_SEARCH_STEP, lambda a: a <= MAX_ANGLE_DEG)

        projectile_vertical_angle = start
        while end_cond(projectile_vertical_angle):
            # 1. 估算初始速度
            pred_v = self.estimate_initial_velocity(projectile_vertical_angle, distance_m, HEIGHT_M)
            if pred_v is None:
                projectile_vertical_angle += step
                continue

            # 2. 线性搜索找到一个能“过顶”的速度区间
            low_v, high_v, found = pred_v, 0.0, False
            for i in range(MAX_VELOCITY_TRIES):
                test_v = low_v + i * VELOCITY_SEARCH_STEP
                hit_h, _ = self.run_simulation_for_angle_and_velocity(projectile_vertical_angle, test_v, distance_m)
                if hit_h > HEIGHT_M:
                    high_v, low_v, found = test_v, max(pred_v, test_v - VELOCITY_SEARCH_STEP), True
                    break
            if not found:
                projectile_vertical_angle += step
                continue

            # 3. 二分法精确查找能命中目标的速度
            for _ in range(BISECTION_ITERATIONS):
                mid_v = (low_v + high_v) / 2.0
                if mid_v <= 0: break
                mid_h, _ = self.run_simulation_for_angle_and_velocity(projectile_vertical_angle, mid_v, distance_m)
                if mid_h > HEIGHT_M:
                    high_v = mid_v
                else:
                    low_v = mid_v

            projectile_total_velocity = high_v  # 使用上界作为最终速度
            final_h, final_t = self.run_simulation_for_angle_and_velocity(projectile_vertical_angle,
                                                                          projectile_total_velocity, distance_m)

            # 4. 如果命中，则计算发射器的实际参数
            if abs(final_h - HEIGHT_M) <= HIT_TOLERANCE_M:
                # 投射物在水平和垂直方向的速度分量 (在世界坐标系)
                v_projectile_h_magnitude = projectile_total_velocity * math.cos(math.radians(projectile_vertical_angle))
                v_projectile_v = projectile_total_velocity * math.sin(math.radians(projectile_vertical_angle))

                # 投射物水平速度矢量
                v_projectile_h_vec = np.array([v_projectile_h_magnitude * math.cos(target_dir_rad),
                                               v_projectile_h_magnitude * math.sin(target_dir_rad)])

                # 关键：发射器速度 = 投射物速度 - 机器人速度 (矢量减法)
                v_launcher_h_vec = v_projectile_h_vec - v_vehicle_vec
                v_launcher_h_magnitude = np.linalg.norm(v_launcher_h_vec)
                aim_azimuth_rad = math.atan2(v_launcher_h_vec[1], v_launcher_h_vec[0])

                # 发射器的垂直速度不受机器人平动影响
                v_launcher_v = v_projectile_v
                # 合成发射器的总速度和俯仰角
                launcher_velocity = math.sqrt(v_launcher_h_magnitude ** 2 + v_launcher_v ** 2)
                launcher_angle_deg = math.degrees(math.atan2(v_launcher_v, v_launcher_h_magnitude))

                # 寻找总发射速度最小的解
                if launcher_velocity < last_min_launcher_v:
                    last_min_launcher_v = launcher_velocity
                    min_v_sol = {
                        'launcher_velocity': launcher_velocity,
                        'launcher_angle': launcher_angle_deg,
                        'aim_azimuth_deg': math.degrees(aim_azimuth_rad),
                        'time': final_t,
                        'projectile_total_velocity': projectile_total_velocity,
                        'projectile_vertical_angle': projectile_vertical_angle,
                    }
                else:
                    # 如果当前解的速度比上一个找到的最小速度解要大，说明我们已经越过了最优解，可以提前退出
                    break
            projectile_vertical_angle += step
        return min_v_sol


if __name__ == "__main__":
    root = tk.Tk()
    app = FieldViewerApp(root)
    root.mainloop()