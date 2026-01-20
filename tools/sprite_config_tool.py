import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import json
import os

class SpriteConfigTool:
    def __init__(self, root):
        self.root = root
        self.root.title("精灵图集配置工具")
        self.root.geometry("1000x700")
        
        # 初始化变量
        self.image_path = ""
        self.image = None
        self.photo_image = None
        self.canvas = None
        self.image_id = None
        self.selected_rect = None
        self.current_sprite = {}
        self.sprites = {}
        self.dragging = False
        self.start_x = 0
        self.start_y = 0
        
        # 创建菜单
        self.create_menu()
        
        # 创建主布局
        self.create_layout()
        
    def create_menu(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        
        # 文件菜单
        file_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="打开图集", command=self.open_image)
        file_menu.add_command(label="打开配置", command=self.open_json)
        file_menu.add_command(label="保存配置", command=self.save_json)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        
    def create_layout(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 设置行列权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 左侧预览区域
        preview_frame = ttk.LabelFrame(main_frame, text="图集预览", padding="5")
        preview_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        
        # 创建画布
        self.canvas = tk.Canvas(preview_frame, bg="gray")
        self.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        
        # 右侧放大预览区域
        zoom_preview_frame = ttk.LabelFrame(main_frame, text="放大预览", padding="5")
        zoom_preview_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        zoom_preview_frame.columnconfigure(0, weight=1)
        zoom_preview_frame.rowconfigure(0, weight=1)
        
        # 创建放大预览画布
        self.zoom_canvas = tk.Canvas(zoom_preview_frame, bg="black", width=300, height=300)
        self.zoom_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 右侧属性面板
        prop_frame = ttk.LabelFrame(main_frame, text="精灵属性", padding="5")
        prop_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.E), padx=5, pady=5)
        
        # 精灵ID输入
        ttk.Label(prop_frame, text="精灵ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.sprite_id_entry = ttk.Entry(prop_frame, width=20)
        self.sprite_id_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=2)
        
        # 矩形坐标显示
        ttk.Label(prop_frame, text="矩形坐标:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.rect_label = ttk.Label(prop_frame, text="x: 0, y: 0, w: 0, h: 0")
        self.rect_label.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # 中心点设置
        ttk.Label(prop_frame, text="中心点 X:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.center_x_entry = ttk.Entry(prop_frame, width=10)
        self.center_x_entry.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(prop_frame, text="中心点 Y:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.center_y_entry = ttk.Entry(prop_frame, width=10)
        self.center_y_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # 碰撞半径设置
        ttk.Label(prop_frame, text="碰撞半径:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.radius_entry = ttk.Entry(prop_frame, width=10)
        self.radius_entry.insert(0, "8.0")
        self.radius_entry.grid(row=4, column=1, sticky=tk.W, pady=2)
        
        # 旋转设置
        ttk.Label(prop_frame, text="是否旋转:").grid(row=5, column=0, sticky=tk.W, pady=2)
        self.rotate_var = tk.BooleanVar(value=True)
        self.rotate_check = ttk.Checkbutton(prop_frame, variable=self.rotate_var)
        self.rotate_check.grid(row=5, column=1, sticky=tk.W, pady=2)
        
        # 添加精灵按钮
        self.add_sprite_btn = ttk.Button(prop_frame, text="添加精灵", command=self.add_sprite)
        self.add_sprite_btn.grid(row=6, column=0, columnspan=2, pady=5)
        
        # 保存修改按钮
        self.save_edit_btn = ttk.Button(prop_frame, text="保存修改", command=self.save_sprite_edit)
        self.save_edit_btn.grid(row=7, column=0, columnspan=2, pady=5)
        
        # 保存配置按钮
        self.save_btn = ttk.Button(prop_frame, text="保存配置", command=self.save_json)
        self.save_btn.grid(row=8, column=0, columnspan=2, pady=5)
        
        # 精灵列表
        sprite_list_frame = ttk.LabelFrame(main_frame, text="精灵列表", padding="5")
        sprite_list_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        sprite_list_frame.columnconfigure(0, weight=1)
        sprite_list_frame.rowconfigure(0, weight=1)
        
        # 创建精灵列表树
        columns = ("id", "rect", "center", "radius", "rotating")
        self.sprite_tree = ttk.Treeview(sprite_list_frame, columns=columns, show="headings", height=10)
        
        # 设置列标题
        for col in columns:
            self.sprite_tree.heading(col, text=col)
            if col == "id":
                self.sprite_tree.column(col, width=100)
            elif col == "rect":
                self.sprite_tree.column(col, width=150)
            elif col == "center":
                self.sprite_tree.column(col, width=100)
            elif col == "radius":
                self.sprite_tree.column(col, width=80)
            elif col == "rotating":
                self.sprite_tree.column(col, width=80)
        
        self.sprite_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(sprite_list_frame, orient=tk.VERTICAL, command=self.sprite_tree.yview)
        self.sprite_tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 绑定事件
        self.sprite_tree.bind("<Double-1>", self.edit_sprite)
        self.sprite_tree.bind("<Button-1>", self.show_selected_sprite_preview)
        
    def open_image(self):
        # 打开文件选择对话框
        file_path = filedialog.askopenfilename(
            filetypes=[("图像文件", "*.png;*.jpg;*.jpeg;*.bmp")]
        )
        
        if file_path:
            self.image_path = file_path
            self.load_image()
            
    def open_json(self):
        # 打开JSON配置文件
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    sprite_data = json.load(f)
                
                # 提取图片文件名
                if "__image_filename" in sprite_data:
                    image_filename = sprite_data["__image_filename"]
                    # 尝试从JSON文件所在目录加载图片
                    json_dir = os.path.dirname(file_path)
                    image_path = os.path.join(json_dir, image_filename)
                    
                    # 尝试在不同位置查找图片文件
                    possible_paths = [
                        image_path,  # 原始路径
                        os.path.join(json_dir, 'bullet', image_filename),  # 尝试在bullet子目录
                        os.path.join(os.path.dirname(json_dir), image_filename),  # 尝试在上一级目录
                        os.path.join(os.path.dirname(json_dir), 'bullet', image_filename)  # 尝试在上一级目录的bullet子目录
                    ]
                    
                    # 找到第一个存在的路径
                    valid_image_path = None
                    for path in possible_paths:
                        if os.path.exists(path):
                            valid_image_path = path
                            break
                    
                    if valid_image_path:
                        self.image_path = valid_image_path
                        self.load_image()
                        
                        # 提取精灵数据
                        self.sprites = {}
                        for key, value in sprite_data.items():
                            if key != "__image_filename":
                                # 处理新格式（sprites字段）
                                if key == "sprites":
                                    for sprite_id, sprite_config in value.items():
                                        self.sprites[sprite_id] = {
                                            "rect": sprite_config.get("rect", [0, 0, 0, 0]),
                                            "center": sprite_config.get("center", [0, 0]),
                                            "radius": sprite_config.get("radius", 0.0),
                                            "is_rotating": sprite_config.get("is_rotating", False)
                                        }
                                else:
                                    # 旧格式直接添加
                                    self.sprites[key] = value
                        
                        # 刷新精灵列表
                        self.refresh_sprite_list()
                        messagebox.showinfo("成功", "配置文件加载成功！")
                    else:
                        # 显示所有尝试过的路径，方便用户排查问题
                        error_message = f"无法找到图片文件：{image_filename}\n\n尝试过的路径：\n"
                        for path in possible_paths:
                            error_message += f"- {path}\n"
                        messagebox.showerror("错误", error_message)
                else:
                    messagebox.showerror("错误", "JSON文件中没有包含图片文件名信息")
                
            except Exception as e:
                messagebox.showerror("错误", f"加载JSON文件失败：{str(e)}")
    
    def load_image(self):
        # 加载图片
        self.image = Image.open(self.image_path)
        
        # 调整图片大小以适应画布
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # 计算缩放比例
        scale = min(canvas_width / self.image.width, canvas_height / self.image.height)
        new_width = int(self.image.width * scale)
        new_height = int(self.image.height * scale)
        
        # 缩放图片
        resized_image = self.image.resize((new_width, new_height), Image.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(resized_image)
        
        # 清除画布并显示图片
        self.canvas.delete("all")
        self.image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
        
        # 记录缩放比例，用于后续绘制精灵和判定点
        self.scale_factor = scale
        
        # 从图片文件名生成默认精灵ID前缀
        self.image_filename = os.path.basename(self.image_path)
        self.image_name = os.path.splitext(self.image_filename)[0]
        
    def on_mouse_down(self, event):
        # 记录鼠标按下的位置
        self.dragging = True
        self.start_x = event.x
        self.start_y = event.y
        
        # 如果已经有选择的矩形，删除它
        if self.selected_rect:
            self.canvas.delete(self.selected_rect)
            self.selected_rect = None
        
    def on_mouse_drag(self, event):
        if not self.dragging:
            return
        
        # 计算矩形的坐标和大小
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        
        # 创建或更新矩形
        if self.selected_rect:
            self.canvas.delete(self.selected_rect)
        
        self.selected_rect = self.canvas.create_rectangle(
            x1, y1, x2, y2, outline="red", width=2
        )
        
        # 更新矩形坐标显示
        self.update_rect_label(x1, y1, x2 - x1, y2 - y1)
        
        # 更新中心点输入框的默认值（矩形中心）
        center_x = int((x2 - x1) / 2)
        center_y = int((y2 - y1) / 2)
        self.center_x_entry.delete(0, tk.END)
        self.center_x_entry.insert(0, str(center_x))
        self.center_y_entry.delete(0, tk.END)
        self.center_y_entry.insert(0, str(center_y))
        
    def on_mouse_up(self, event):
        self.dragging = False
        
        # 自动生成精灵ID
        if self.selected_rect and hasattr(self, 'image_name'):
            # 获取矩形坐标
            rect_coords = self.canvas.coords(self.selected_rect)
            x, y, x2, y2 = rect_coords
            width, height = x2 - x, y2 - y
            
            # 生成精灵ID: 图片名_x_y_width_height
            sprite_id = f"{self.image_name}_{int(x)}_{int(y)}_{int(width)}_{int(height)}"
            
            # 检查是否已存在同名精灵
            counter = 1
            original_id = sprite_id
            while sprite_id in self.sprites:
                sprite_id = f"{original_id}_{counter}"
                counter += 1
            
            # 填充精灵ID输入框
            self.sprite_id_entry.delete(0, tk.END)
            self.sprite_id_entry.insert(0, sprite_id)
        
    def update_rect_label(self, x, y, width, height):
        # 更新矩形坐标标签
        self.rect_label.config(text=f"x: {x}, y: {y}, w: {width}, h: {height}")
        
    def add_sprite(self):
        # 获取精灵ID
        sprite_id = self.sprite_id_entry.get().strip()
        if not sprite_id:
            messagebox.showerror("错误", "精灵ID不能为空")
            return
        
        # 获取矩形坐标
        rect_text = self.rect_label.cget("text")
        if rect_text == "x: 0, y: 0, w: 0, h: 0":
            messagebox.showerror("错误", "请先在图集中选择一个区域")
            return
        
        # 解析矩形坐标
        try:
            # 从字符串中提取数字
            parts = rect_text.split(", ")
            x = int(parts[0].split(": ")[1])
            y = int(parts[1].split(": ")[1])
            width = int(parts[2].split(": ")[1])
            height = int(parts[3].split(": ")[1])
        except (IndexError, ValueError):
            messagebox.showerror("错误", "矩形坐标解析失败")
            return
        
        # 获取中心点
        try:
            center_x = int(self.center_x_entry.get())
            center_y = int(self.center_y_entry.get())
        except ValueError:
            messagebox.showerror("错误", "中心点坐标必须是整数")
            return
        
        # 获取碰撞半径
        try:
            radius = float(self.radius_entry.get())
        except ValueError:
            messagebox.showerror("错误", "碰撞半径必须是数字")
            return
        
        # 获取旋转设置
        rotating = self.rotate_var.get()
        
        # 创建精灵配置
        sprite_config = {
            "rect": [x, y, width, height],
            "center": [center_x, center_y],
            "radius": radius,
            "is_rotating": rotating
        }
        
        # 添加到精灵字典
        self.sprites[sprite_id] = sprite_config
        
        # 刷新精灵列表
        self.refresh_sprite_list()
        
        # 清除选择的矩形和输入
        if self.selected_rect:
            self.canvas.delete(self.selected_rect)
            self.selected_rect = None
        self.sprite_id_entry.delete(0, tk.END)
        self.update_rect_label(0, 0, 0, 0)
        self.center_x_entry.delete(0, tk.END)
        self.center_y_entry.delete(0, tk.END)
        
    def refresh_sprite_list(self):
        # 清空树
        for item in self.sprite_tree.get_children():
            self.sprite_tree.delete(item)
        
        # 添加精灵到树中
        for sprite_id, config in self.sprites.items():
            rect_str = f"{config['rect']}"
            center_str = f"{config['center']}"
            radius_str = f"{config['radius']}"
            rotating_str = "是" if config['is_rotating'] else "否"
            
            self.sprite_tree.insert("", tk.END, values=(sprite_id, rect_str, center_str, radius_str, rotating_str))
        
    def edit_sprite(self, event):
        # 获取选中的精灵
        selected_item = self.sprite_tree.selection()[0]
        sprite_id = self.sprite_tree.item(selected_item, "values")[0]
        
        # 获取精灵配置
        config = self.sprites[sprite_id]
        
        # 显示到界面
        self.sprite_id_entry.delete(0, tk.END)
        self.sprite_id_entry.insert(0, sprite_id)
        
        rect = config['rect']
        self.update_rect_label(rect[0], rect[1], rect[2], rect[3])
        
        self.center_x_entry.delete(0, tk.END)
        self.center_x_entry.insert(0, str(config['center'][0]))
        self.center_y_entry.delete(0, tk.END)
        self.center_y_entry.insert(0, str(config['center'][1]))
        
        self.radius_entry.delete(0, tk.END)
        self.radius_entry.insert(0, str(config['radius']))
        
        self.rotate_var.set(config['is_rotating'])
        
        # 记录当前正在编辑的精灵ID
        self.current_edit_id = sprite_id
    
    def save_sprite_edit(self):
        # 获取当前正在编辑的精灵ID
        if hasattr(self, 'current_edit_id') and self.current_edit_id in self.sprites:
            sprite_id = self.current_edit_id
        else:
            # 如果没有记录正在编辑的ID，尝试从输入框获取
            sprite_id = self.sprite_id_entry.get().strip()
            if not sprite_id or sprite_id not in self.sprites:
                messagebox.showerror("错误", "请先选择要编辑的精灵")
                return
        
        # 获取修改后的属性值
        try:
            # 解析矩形坐标
            rect_text = self.rect_label.cget("text")
            parts = rect_text.split(", ")
            x = int(parts[0].split(": ")[1])
            y = int(parts[1].split(": ")[1])
            width = int(parts[2].split(": ")[1])
            height = int(parts[3].split(": ")[1])
            rect = [x, y, width, height]
            
            # 获取中心点
            center_x = int(self.center_x_entry.get())
            center_y = int(self.center_y_entry.get())
            center = [center_x, center_y]
            
            # 获取碰撞半径
            radius = float(self.radius_entry.get())
            
            # 获取旋转设置
            rotating = self.rotate_var.get()
            
            # 更新精灵配置
            self.sprites[sprite_id] = {
                "rect": rect,
                "center": center,
                "radius": radius,
                "is_rotating": rotating
            }
            
            # 刷新精灵列表
            self.refresh_sprite_list()
            
            # 清除当前编辑状态
            delattr(self, 'current_edit_id')
            
            messagebox.showinfo("成功", f"精灵 {sprite_id} 的修改已保存")
            
        except (IndexError, ValueError) as e:
            messagebox.showerror("错误", f"属性值解析失败：{str(e)}")
            return
        
    def save_json(self):
        if not self.sprites:
            messagebox.showwarning("警告", "没有精灵数据可以保存")
            return
        
        # 默认保存路径为图片所在目录，使用图片名作为JSON文件名
        if hasattr(self, 'image_path') and self.image_path:
            image_dir = os.path.dirname(self.image_path)
            json_filename = f"{self.image_name}.json"
            default_path = os.path.join(image_dir, json_filename)
        else:
            image_dir = ""
            json_filename = "bullet_defs.json"
            default_path = json_filename
        
        # 打开文件保存对话框
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")],
            initialfile=json_filename,
            initialdir=image_dir
        )
        
        if file_path:
            # 保存JSON文件
            with open(file_path, "w", encoding="utf-8") as f:
                # 添加图片路径信息到JSON中
                sprite_data = self.sprites.copy()
                if hasattr(self, 'image_filename'):
                    sprite_data['__image_filename'] = self.image_filename
                
                json.dump(sprite_data, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("成功", f"配置文件已保存到：{file_path}")
    
    def show_selected_sprite_preview(self, event):
        # 显示选中精灵的放大预览
        selected_item = self.sprite_tree.selection()
        if not selected_item:
            return
            
        selected_item = selected_item[0]
        sprite_id = self.sprite_tree.item(selected_item, "values")[0]
        
        # 获取精灵配置
        if sprite_id not in self.sprites:
            return
            
        sprite_config = self.sprites[sprite_id]
        rect = sprite_config['rect']
        center = sprite_config['center']
        radius = sprite_config['radius']
        
        # 清除放大预览画布
        self.zoom_canvas.delete("all")
        
        if self.image is None:
            return
            
        # 计算精灵在原图中的位置和大小
        x1, y1, width, height = rect
        x2 = x1 + width
        y2 = y1 + height
        
        # 从原图中裁剪精灵
        sprite_image = self.image.crop((x1, y1, x2, y2))
        
        # 放大精灵（例如放大4倍）
        zoom_factor = 4
        zoomed_width = width * zoom_factor
        zoomed_height = height * zoom_factor
        zoomed_image = sprite_image.resize((zoomed_width, zoomed_height), Image.LANCZOS)
        
        # 创建PhotoImage
        self.zoomed_photo = ImageTk.PhotoImage(zoomed_image)
        
        # 计算居中显示的位置
        canvas_width = self.zoom_canvas.winfo_width()
        canvas_height = self.zoom_canvas.winfo_height()
        x_offset = (canvas_width - zoomed_width) // 2
        y_offset = (canvas_height - zoomed_height) // 2
        
        # 在放大预览画布上显示精灵
        self.zoom_canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.zoomed_photo)
        
        # 显示判定点（中心点）
        center_x = x_offset + center[0] * zoom_factor
        center_y = y_offset + center[1] * zoom_factor
        self.zoom_canvas.create_oval(
            center_x - 3, center_y - 3, center_x + 3, center_y + 3,
            fill="red", outline="white"
        )
        
        # 显示判定范围（碰撞半径）
        radius_pixels = radius * zoom_factor
        self.zoom_canvas.create_oval(
            center_x - radius_pixels, center_y - radius_pixels,
            center_x + radius_pixels, center_y + radius_pixels,
            outline="green", width=2
        )

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteConfigTool(root)
    root.mainloop()