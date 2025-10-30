"""
    注释由 Gemini 2.5 Pro 提供
"""

import tkinter as tk
from tkinter import font as tkFont
from tkinter import messagebox  # <--- 新增/修改
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
# 这些是固定的物理尺寸，不应在UI中更改
REAL_FIELD_SIZE = 141.170031  # 场地的实际尺寸 (宽度/高度)
REAL_PANEL_LENGTH = 27.889412  # 场地角落斜板的实际长度
FIELD_SIZE = 1.0  # 标准化场地尺寸，用于内部计算
NORMALIZED_PANEL_LENGTH = REAL_PANEL_LENGTH / REAL_FIELD_SIZE  # 标准化斜板长度
ANGLE_WITH_SIDE_WALL_DEG = 54.046000  # 斜板与侧墙的夹角 (度)
INCHES_TO_METERS = 0.0254  # 英寸到米的转换系数


class PreferencesWindow(tk.Toplevel):  # <--- 新增/修改 (整个类)
    """用于配置程序常量的弹出窗口"""

    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.transient(master)  # 使窗口显示在主窗口之上
        self.title("Preferences")
        self.geometry("450x650")
        self.resizable(False, False)

        # 用于存储与输入框关联的Tkinter变量
        self.vars = {}

        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- 物理常量 ---
        physics_frame = tk.LabelFrame(main_frame, text="Physics Constants", padx=10, pady=10)
        physics_frame.pack(fill=tk.X, pady=5)
        self.create_entry(physics_frame, "Gravity (m/s^2)", "GRAVITY_MS2", self.app.GRAVITY_MS2)
        self.create_entry(physics_frame, "Air Density (kg/m^3)", "AIR_DENSITY", self.app.AIR_DENSITY)
        self.create_entry(physics_frame, "Target Height (m)", "HEIGHT_M", self.app.HEIGHT_M)
        self.create_entry(physics_frame, "Projectile Mass (kg)", "MASS_KG", self.app.MASS_KG)
        self.create_entry(physics_frame, "Drag Coefficient", "DRAG_COEFFICIENT", self.app.DRAG_COEFFICIENT)
        self.create_entry(physics_frame, "Cross Section (m^2)", "CROSS_SECTIONAL_AREA_M2",
                          self.app.CROSS_SECTIONAL_AREA_M2)

        # --- 计算参数 ---
        calc_frame = tk.LabelFrame(main_frame, text="Calculation Parameters", padx=10, pady=10)
        calc_frame.pack(fill=tk.X, pady=5)
        self.create_entry(calc_frame, "Min Search Angle (deg)", "MIN_ANGLE_DEG", self.app.MIN_ANGLE_DEG)
        self.create_entry(calc_frame, "Max Search Angle (deg)", "MAX_ANGLE_DEG", self.app.MAX_ANGLE_DEG)
        self.create_entry(calc_frame, "Angle Search Step (deg)", "ANGLE_SEARCH_STEP", self.app.ANGLE_SEARCH_STEP)
        self.create_entry(calc_frame, "Velocity Search Step (m/s)", "VELOCITY_SEARCH_STEP",
                          self.app.VELOCITY_SEARCH_STEP)
        self.create_entry(calc_frame, "Max Velocity Tries", "MAX_VELOCITY_TRIES", self.app.MAX_VELOCITY_TRIES)
        self.create_entry(calc_frame, "Bisection Iterations", "BISECTION_ITERATIONS", self.app.BISECTION_ITERATIONS)
        self.create_entry(calc_frame, "Hit Tolerance (m)", "HIT_TOLERANCE_M", self.app.HIT_TOLERANCE_M)
        self.create_entry(calc_frame, "Simulation Timestep (s)", "TIME_STEP_S", self.app.TIME_STEP_S)

        # --- 发射器硬件 ---
        hardware_frame = tk.LabelFrame(main_frame, text="Launcher Hardware Constants", padx=10, pady=10)
        hardware_frame.pack(fill=tk.X, pady=5)
        self.create_entry(hardware_frame, "Motor RPM Loss Factor (%)", "MOTOR_RPM_LOSS_FACTOR_PERCENT",
                          self.app.MOTOR_RPM_LOSS_FACTOR_PERCENT)
        self.create_entry(hardware_frame, "Friction Wheel Diameter (m)", "FRICTION_WHEEL_DIAMETER_M",
                          self.app.FRICTION_WHEEL_DIAMETER_M)

        # --- 按钮 ---
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        tk.Button(button_frame, text="Save", command=self.save_and_close).pack(side=tk.RIGHT, padx=5)
        tk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        self.grab_set()  # 模态化窗口，阻止用户与主窗口交互

    def create_entry(self, parent, label_text, attr_name, current_value):
        """辅助函数，用于创建标签和输入框对"""
        frame = tk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        tk.Label(frame, text=label_text, width=25, anchor='w').pack(side=tk.LEFT)
        var = tk.StringVar(value=str(current_value))
        self.vars[attr_name] = var
        tk.Entry(frame, textvariable=var).pack(side=tk.RIGHT, fill=tk.X, expand=True)

    def save_and_close(self):
        """保存更改并关闭窗口"""
        try:
            for attr_name, var in self.vars.items():
                # 根据属性名称获取原始类型（整数或浮点数）
                original_value = getattr(self.app, attr_name)
                if isinstance(original_value, int):
                    new_value = int(var.get())
                else:
                    new_value = float(var.get())
                # 更新主应用实例中的属性
                setattr(self.app, attr_name, new_value)
            self.destroy()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please ensure all values are valid numbers.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self)


class FieldViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("The Archer | Powered by 27570")
        self.root.geometry("1280x720")
        self.root.resizable(False, False)

        # --- 将可配置常量移至实例属性 --- # <--- 新增/修改
        self.load_configurable_constants()

        # --- UI 界面常量 (固定) ---
        self.CANVAS_SIZE_PX = 680
        self.RIGHT_PANEL_WIDTH = 570
        self.PADDING_PX = 20

        # 设置用于线程通信的队列
        self.calc_queue = queue.Queue(maxsize=1)
        self.result_queue = queue.Queue()

        self.worker_thread = threading.Thread(target=self.calculation_worker, daemon=True)
        self.worker_thread.start()

        self.last_solution = None
        self.last_calc_params = {}
        self.last_path = ([], [])

        # --- 创建菜单栏 --- # <--- 新增/修改
        self.menu_bar = tk.Menu(root)
        self.root.config(menu=self.menu_bar)
        self.edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Edit", menu=self.edit_menu)
        self.edit_menu.add_command(label="Preferences...", command=self.open_preferences)
        # --- 菜单栏创建结束 ---

        # --- UI 布局 ---
        canvas_frame = tk.Frame(root)
        canvas_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        right_panel = tk.Frame(root, width=self.RIGHT_PANEL_WIDTH)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=10)
        right_panel.pack_propagate(False)

        self.canvas = tk.Canvas(canvas_frame, width=self.CANVAS_SIZE_PX, height=self.CANVAS_SIZE_PX, bg="white")
        self.canvas.pack()

        self.controls_frame = tk.Frame(right_panel)
        self.controls_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        plot_frame = tk.Frame(right_panel)
        plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        self.fig = Figure(dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.plot_canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.plot_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.title_font = tkFont.Font(family="Arial", size=12, weight="bold")
        self.label_font = tkFont.Font(family="Consolas", size=10)
        self.bold_label_font = tkFont.Font(family="Consolas", size=11, weight="bold")
        self.credit_font = tkFont.Font(family="Arial", size=9, slant="italic")

        self.setup_controls()

        self.field_bg_image = None
        try:
            draw_size = self.CANVAS_SIZE_PX - 2 * self.PADDING_PX
            original_image = Image.open("ttt.jpg")
            image_with_alpha = original_image.convert("RGBA")
            pixel_data = image_with_alpha.getdata()
            new_pixel_data = []
            alpha_value = int(255 * (1.0 - 0.7))
            for item in pixel_data:
                new_pixel_data.append((item[0], item[1], item[2], alpha_value))
            image_with_alpha.putdata(new_pixel_data)
            resized_image = image_with_alpha.resize((draw_size, draw_size), Image.Resampling.LANCZOS)
            self.field_bg_image = ImageTk.PhotoImage(resized_image)
        except FileNotFoundError:
            print("Warning: 'ttt.jpg' not found. Using a white background.")
        except Exception as e:
            print(f"Error loading background image: {e}")

        self.drag_pos_x, self.drag_pos_y = 0.5, 0.5
        self.calculate_geometry()
        self.draw_static_field()
        self.draw_interactive_elements()

        self.root.after(30, self.process_results)
        self.canvas.bind("<Button-1>", self.on_mouse_action)
        self.canvas.bind("<B1-Motion>", self.on_mouse_action)

    def load_configurable_constants(self):  # <--- 新增/修改 (整个方法)
        """将所有可配置的常量加载为实例属性"""
        # --- 物理常量 ---
        self.GRAVITY_MS2 = 9.81
        self.AIR_DENSITY = 1.225
        self.HEIGHT_M = 1.065
        self.MASS_KG = 0.012
        self.DRAG_COEFFICIENT = 0.25
        self.CROSS_SECTIONAL_AREA_M2 = 0.00928

        # --- 计算参数 ---
        self.MIN_ANGLE_DEG = 55.0
        self.MAX_ANGLE_DEG = 90.0
        self.ANGLE_SEARCH_STEP = 1.0
        self.VELOCITY_SEARCH_STEP = 0.1
        self.MAX_VELOCITY_TRIES = 500
        self.BISECTION_ITERATIONS = 8
        self.HIT_TOLERANCE_M = 0.055
        self.TIME_STEP_S = 0.006

        # --- 发射器硬件常量 ---
        self.MOTOR_RPM_LOSS_FACTOR_PERCENT = 55
        self.FRICTION_WHEEL_DIAMETER_M = 0.072

    def open_preferences(self):  # <--- 新增/修改
        """打开首选项配置窗口"""
        prefs_window = PreferencesWindow(self.root, self)
        # 等待首选项窗口关闭后，重新触发一次计算，以应用新的常量
        self.root.wait_window(prefs_window)
        self.draw_interactive_elements()

    def setup_controls(self):
        self.controls_frame.columnconfigure(0, weight=0)
        self.controls_frame.columnconfigure(1, weight=1)
        row_idx = 0

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

        tk.Frame(self.controls_frame, height=2, bg="lightgray").grid(row=row_idx, column=0, columnspan=2, sticky='ew',
                                                                     pady=10)
        row_idx += 1

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

        tk.Frame(self.controls_frame, height=2, bg="lightgray").grid(row=row_idx, column=0, columnspan=2, sticky='ew',
                                                                     pady=10)
        row_idx += 1

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

        tk.Frame(self.controls_frame, height=2, bg="lightgray").grid(row=row_idx, column=0, columnspan=2, sticky='ew',
                                                                     pady=10)
        row_idx += 1

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

        tk.Label(self.controls_frame, text="Est. Motor RPM:", font=self.bold_label_font, fg="#008000").grid(row=row_idx,
                                                                                                           column=0,
                                                                                                           sticky='w',
                                                                                                           padx=5)
        self.motor_rpm_label = tk.Label(self.controls_frame, text="--", font=self.label_font, fg="#008000")
        self.motor_rpm_label.grid(row=row_idx, column=1, sticky='w', padx=5)
        row_idx += 1

        tk.Label(self.controls_frame, text="").grid(row=row_idx, column=0)
        row_idx += 1

        credit_label = tk.Label(self.controls_frame, text="Programmed by BlueDarkUP", font=self.credit_font,
                                fg="gray")
        credit_label.grid(row=row_idx, column=0, columnspan=2, sticky='e', padx=5)

    def on_toggle_plot(self):
        self.update_plot(self.last_solution, self.last_calc_params.get('distance_m', 0), self.last_path)

    def on_motion_change(self, _=None):
        self.draw_interactive_elements()

    def calculate_motor_rpm(self, velocity_ms):
        if velocity_ms <= 0:
            return 0
        theoretical_rpm = (velocity_ms * 60) / (math.pi * self.FRICTION_WHEEL_DIAMETER_M)
        estimated_rpm = theoretical_rpm * (1 + self.MOTOR_RPM_LOSS_FACTOR_PERCENT / 100.0)
        return estimated_rpm

    def calculation_worker(self):
        while True:
            try:
                calc_params = self.calc_queue.get()
                solution = self.find_launch_solution(calc_params)
                self.result_queue.put((calc_params, solution))
            except Exception as e:
                print(f"Error in calculation worker: {e}")

    def process_results(self):
        latest_result = None
        while not self.result_queue.empty():
            try:
                latest_result = self.result_queue.get_nowait()
            except queue.Empty:
                break

        if latest_result:
            calc_params, solution = latest_result
            self.update_solution_display(solution, calc_params)

        self.root.after(30, self.process_results)

    def update_solution_display(self, solution, calc_params):
        self.last_solution = solution
        self.last_calc_params = calc_params
        distance_m = calc_params.get('distance_m', 0)

        path = ([], [])
        if solution:
            self.launch_angle_label.config(text=f"{solution['launcher_angle']:.2f} deg")
            self.aim_azimuth_label.config(text=f"{solution['aim_azimuth_deg']:.2f} deg")
            self.launch_velocity_label.config(text=f"{solution['launcher_velocity']:.2f} m/s")

            estimated_rpm = self.calculate_motor_rpm(solution['launcher_velocity'])
            self.motor_rpm_label.config(text=f"~{estimated_rpm:.0f} RPM")

            _, _, path_x, path_y = self.run_simulation_for_angle_and_velocity(
                solution['projectile_vertical_angle'], solution['projectile_total_velocity'], distance_m,
                return_path=True
            )
            path = (path_x, path_y)
        else:
            self.launch_angle_label.config(text="N/A")
            self.aim_azimuth_label.config(text="N/A")
            self.launch_velocity_label.config(text="N/A")
            self.motor_rpm_label.config(text="N/A")

        self.last_path = path
        self.draw_interactive_elements()
        self.update_plot(solution, distance_m, path)

    def on_mouse_action(self, event):
        fx, fy = self.canvas_to_field(event.x, event.y)
        self.drag_pos_x = max(0.0, min(1.0, fx))
        self.drag_pos_y = max(0.0, min(1.0, fy))
        self.draw_interactive_elements()

    def draw_interactive_elements(self):
        self.canvas.delete("interactive")
        point_px = self.field_to_canvas(self.drag_pos_x, self.drag_pos_y)
        current_point_norm = np.array([self.drag_pos_x, self.drag_pos_y])

        self.canvas.create_line(self.field_to_canvas(self.drag_pos_x, 1.0), self.field_to_canvas(self.drag_pos_x, 0.0),
                                fill="purple", dash=(5, 5), width=2, tags="interactive")
        self.canvas.create_line(self.field_to_canvas(0.0, self.drag_pos_y), self.field_to_canvas(1.0, self.drag_pos_y),
                                fill="purple", dash=(5, 5), width=2, tags="interactive")

        self.canvas.create_oval(point_px[0] - 8, point_px[1] - 8, point_px[0] + 8, point_px[1] + 8,
                                fill="black", outline="gray", width=2, tags="interactive")

        alliance = self.alliance_var.get()
        target_tag_pos, line_color = (self.tag_right, "red") if alliance == "Red" else (self.tag_left, "blue")
        vector_to_target = target_tag_pos - current_point_norm
        dist_norm = np.linalg.norm(vector_to_target)
        dist_in = dist_norm * REAL_FIELD_SIZE

        if alliance == "Red":
            self.dist_red_label.config(text=f"{dist_in:.2f} in")
            self.dist_blue_label.config(text="--")
        else:
            self.dist_blue_label.config(text=f"{dist_in:.2f} in")
            self.dist_red_label.config(text="--")

        self.canvas.create_line(point_px, self.field_to_canvas(*target_tag_pos), fill=line_color, width=3,
                                arrow=tk.LAST, tags="interactive")

        angle_to_target_deg = math.degrees(math.atan2(vector_to_target[1], vector_to_target[0]))
        self.angle_label.config(text=f"{angle_to_target_deg:+.2f} deg")
        self.coord_label.config(text=f"X={self.drag_pos_x:.3f}, Y={self.drag_pos_y:.3f}")

        vehicle_speed = self.vehicle_speed_ms.get()
        if vehicle_speed > 0.1:
            move_dir_rad = math.radians(self.vehicle_direction_deg.get())
            arrow_len_norm = vehicle_speed * 0.08
            end_norm_x = self.drag_pos_x + arrow_len_norm * math.cos(move_dir_rad)
            end_norm_y = self.drag_pos_y + arrow_len_norm * math.sin(move_dir_rad)
            self.canvas.create_line(point_px, self.field_to_canvas(end_norm_x, end_norm_y),
                                    arrow=tk.LAST, fill="orange", width=4, tags="interactive")

        if self.last_solution:
            aim_azimuth_rad = math.radians(self.last_solution['aim_azimuth_deg'])
            heading_end_x = self.drag_pos_x + 1.5 * math.cos(aim_azimuth_rad)
            heading_end_y = self.drag_pos_y + 1.5 * math.sin(aim_azimuth_rad)
            self.canvas.create_line(point_px, self.field_to_canvas(heading_end_x, heading_end_y),
                                    arrow=tk.LAST, fill="#555555", width=5, dash=(6, 3), tags="interactive")

        try:
            if not self.calc_queue.empty():
                self.calc_queue.get_nowait()
            calc_params = {
                'distance_m': dist_in * INCHES_TO_METERS,
                'vehicle_speed_ms': self.vehicle_speed_ms.get(),
                'vehicle_direction_deg': self.vehicle_direction_deg.get(),
                'target_direction_deg': angle_to_target_deg
            }
            self.calc_queue.put_nowait(calc_params)
        except queue.Full:
            pass
        except queue.Empty:
            pass

    def field_to_canvas(self, x_norm, y_norm):
        draw_size = self.CANVAS_SIZE_PX - 2 * self.PADDING_PX
        return (self.PADDING_PX + x_norm * draw_size, (self.CANVAS_SIZE_PX - self.PADDING_PX) - y_norm * draw_size)

    def canvas_to_field(self, px, py):
        draw_size = self.CANVAS_SIZE_PX - 2 * self.PADDING_PX
        return ((px - self.PADDING_PX) / draw_size, ((self.CANVAS_SIZE_PX - self.PADDING_PX) - py) / draw_size)

    def calculate_geometry(self):
        angle_rad = np.deg2rad(90.0 - ANGLE_WITH_SIDE_WALL_DEG)
        dx, dy = NORMALIZED_PANEL_LENGTH * np.cos(angle_rad), NORMALIZED_PANEL_LENGTH * np.sin(angle_rad)
        self.p1_left, self.p2_left = np.array([dx, 1.0]), np.array([0.0, 1.0 - dy])
        self.tag_left = (self.p1_left + self.p2_left) / 2
        self.p1_right, self.p2_right = np.array([1.0 - dx, 1.0]), np.array([1.0, 1.0 - dy])
        self.tag_right = (self.p1_right + self.p2_right) / 2

    def draw_static_field(self):
        if self.field_bg_image:
            self.canvas.create_image(self.CANVAS_SIZE_PX / 2, self.CANVAS_SIZE_PX / 2,
                                     image=self.field_bg_image, anchor=tk.CENTER)

        bl_px, tr_px = self.field_to_canvas(0, 0), self.field_to_canvas(1, 1)
        self.canvas.create_rectangle(bl_px[0], bl_px[1], tr_px[0], tr_px[1], outline="black", width=3)
        self.canvas.create_line(bl_px[0], bl_px[1], bl_px[0], tr_px[1], fill="gray", width=2, arrow=tk.LAST)
        self.canvas.create_text(bl_px[0] - 15, tr_px[1] + 10, text="Y", anchor="e", font=("Arial", 14, "bold"))
        self.canvas.create_line(bl_px[0], bl_px[1], tr_px[0], bl_px[1], fill="gray", width=2, arrow=tk.LAST)
        self.canvas.create_text(tr_px[0] - 10, bl_px[1] + 15, text="X", anchor="n", font=("Arial", 14, "bold"))
        self.canvas.create_text(bl_px[0] - 10, bl_px[1] + 10, text="(0,0)", anchor="ne")

        self.draw_star(*self.field_to_canvas(*self.tag_left), 10, "blue")
        self.draw_star(*self.field_to_canvas(*self.tag_right), 10, "red")

    def draw_star(self, cx, cy, size, color):
        points = []
        for i in range(5):
            for ang_mult in [i, i + 0.5]:
                ang = np.pi / 2 + ang_mult * 2 * np.pi / 5
                radius = size if ang_mult == i else size / 2
                points.extend([cx + radius * np.cos(ang), cy - radius * np.sin(ang)])
        self.canvas.create_polygon(points, fill=color, outline=color)

    def update_plot(self, solution, distance_m, path):
        self.ax.clear()

        if not self.draw_plot_var.get():
            self.ax.set_title("Trajectory Plotting Disabled")
            self.ax.text(0.5, 0.5, 'Plotting Disabled', ha='center', va='center', fontsize=12, color='gray',
                         transform=self.ax.transAxes)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        elif solution and path and path[0]:
            path_x, path_y = path
            label_text = (
                f"Pitch: {solution['launcher_angle']:.1f}°, " f"Velocity: {solution['launcher_velocity']:.2f} m/s")
            self.ax.plot(path_x, path_y, 'g-', label=label_text)
            self.ax.plot(distance_m, self.HEIGHT_M, 'ro', markersize=8, label="Target")
            self.ax.grid(True)
            self.ax.legend()
            self.ax.set_xlim(left=0)
            self.ax.set_ylim(bottom=0)
            self.ax.set_aspect('equal', adjustable='box')
        else:
            self.ax.set_title("No Valid Solution Found")
            self.ax.grid(True)
            self.ax.set_xlim(left=0)
            self.ax.set_ylim(bottom=0)

        self.fig.tight_layout(pad=0.8)
        self.plot_canvas.draw()

    def run_simulation_for_angle_and_velocity(self, launch_angle_deg, initial_velocity_ms, distance_m,
                                              return_path=False):
        angle_rad = math.radians(launch_angle_deg)
        vx, vy = initial_velocity_ms * math.cos(angle_rad), initial_velocity_ms * math.sin(angle_rad)
        x, y, current_time, prev_time = 0.0, 0.0, 0.0, 0.0
        path_x, path_y = ([0.0], [0.0]) if return_path else (None, None)

        drag_factor = 0.5 * self.AIR_DENSITY * self.DRAG_COEFFICIENT * self.CROSS_SECTIONAL_AREA_M2
        gravity_force_y = -self.MASS_KG * self.GRAVITY_MS2

        while True:
            if (vx <= 0 and x < distance_m) or (y < 0 and vy < 0):
                return (-1.0, -1.0, [], []) if return_path else (-1.0, -1.0)

            prev_x, prev_y, prev_time = x, y, current_time

            v_sq = vx ** 2 + vy ** 2
            if v_sq == 0:
                return (-1.0, -1.0, [], []) if return_path else (-1.0, -1.0)

            v = math.sqrt(v_sq)
            drag = drag_factor * v_sq
            ax, ay = -drag * (vx / v) / self.MASS_KG, (gravity_force_y - drag * (vy / v)) / self.MASS_KG

            vx += ax * self.TIME_STEP_S
            vy += ay * self.TIME_STEP_S
            x += vx * self.TIME_STEP_S
            y += vy * self.TIME_STEP_S
            current_time += self.TIME_STEP_S

            if return_path: path_x.append(x); path_y.append(y)

            if x >= distance_m:
                if (x - prev_x) == 0:
                    hit_h, hit_t = y, current_time
                else:
                    frac = (distance_m - prev_x) / (x - prev_x)
                    hit_h = prev_y + (y - prev_y) * frac
                    hit_t = prev_time + self.TIME_STEP_S * frac

                if return_path:
                    path_x[-1], path_y[-1] = distance_m, hit_h
                    return hit_h, hit_t, path_x, path_y

                return hit_h, hit_t

    def estimate_initial_velocity(self, angle_deg, target_x, target_y):
        angle_rad = math.radians(angle_deg)
        cos_a, tan_a = math.cos(angle_rad), math.tan(angle_rad)
        denominator = 2 * (cos_a ** 2) * (target_x * tan_a - target_y)
        return math.sqrt((self.GRAVITY_MS2 * target_x ** 2) / denominator) if denominator > 0 else None

    def find_launch_solution(self, params):
        distance_m = params['distance_m']
        if distance_m <= 0: return None

        v_vehicle_ms = params['vehicle_speed_ms']
        vehicle_dir_rad = math.radians(params['vehicle_direction_deg'])
        target_dir_rad = math.radians(params['target_direction_deg'])

        v_vehicle_vec = np.array([v_vehicle_ms * math.cos(vehicle_dir_rad),
                                  v_vehicle_ms * math.sin(vehicle_dir_rad)])

        min_v_sol, last_min_launcher_v = None, float('inf')

        start, step, end_cond = (self.MIN_ANGLE_DEG, self.ANGLE_SEARCH_STEP, lambda a: a <= self.MAX_ANGLE_DEG)

        projectile_vertical_angle = start
        while end_cond(projectile_vertical_angle):
            pred_v = self.estimate_initial_velocity(projectile_vertical_angle, distance_m, self.HEIGHT_M)
            if pred_v is None:
                projectile_vertical_angle += step
                continue

            low_v, high_v, found = pred_v, 0.0, False
            for i in range(self.MAX_VELOCITY_TRIES):
                test_v = low_v + i * self.VELOCITY_SEARCH_STEP
                hit_h, _ = self.run_simulation_for_angle_and_velocity(projectile_vertical_angle, test_v, distance_m)
                if hit_h > self.HEIGHT_M:
                    high_v, low_v, found = test_v, max(pred_v, test_v - self.VELOCITY_SEARCH_STEP), True
                    break
            if not found:
                projectile_vertical_angle += step
                continue

            for _ in range(self.BISECTION_ITERATIONS):
                mid_v = (low_v + high_v) / 2.0
                if mid_v <= 0: break
                mid_h, _ = self.run_simulation_for_angle_and_velocity(projectile_vertical_angle, mid_v, distance_m)
                if mid_h > self.HEIGHT_M:
                    high_v = mid_v
                else:
                    low_v = mid_v

            projectile_total_velocity = high_v
            final_h, final_t = self.run_simulation_for_angle_and_velocity(projectile_vertical_angle,
                                                                          projectile_total_velocity, distance_m)

            if abs(final_h - self.HEIGHT_M) <= self.HIT_TOLERANCE_M:
                v_projectile_h_magnitude = projectile_total_velocity * math.cos(
                    math.radians(projectile_vertical_angle))
                v_projectile_v = projectile_total_velocity * math.sin(math.radians(projectile_vertical_angle))

                v_projectile_h_vec = np.array([v_projectile_h_magnitude * math.cos(target_dir_rad),
                                               v_projectile_h_magnitude * math.sin(target_dir_rad)])

                v_launcher_h_vec = v_projectile_h_vec - v_vehicle_vec
                v_launcher_h_magnitude = np.linalg.norm(v_launcher_h_vec)
                aim_azimuth_rad = math.atan2(v_launcher_h_vec[1], v_launcher_h_vec[0])

                v_launcher_v = v_projectile_v
                launcher_velocity = math.sqrt(v_launcher_h_magnitude ** 2 + v_launcher_v ** 2)
                launcher_angle_deg = math.degrees(math.atan2(v_launcher_v, v_launcher_h_magnitude))

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
                    break
            projectile_vertical_angle += step
        return min_v_sol


if __name__ == "__main__":
    root = tk.Tk()
    app = FieldViewerApp(root)
    root.mainloop()
