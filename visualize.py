import tkinter as tk
from tkinter import ttk
from tkinter import *
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.widgets import Button, TextBox
from matplotlib import colors
from matplotlib.patches import Patch
import sys
import json
import signal


DEFAULT_JSON_PATH = 'results.json'
def mix_colors(c1, c2, ratio):
    """Linearly interpolate between two RGB tuples."""
    return tuple(c1[i] * (1 - ratio) + c2[i] * ratio for i in range(3))

def classify_color(num_nofaults, num_faults, num_crashes, num_resets, num_soft_bricked, num_hard_bricked, num_skipped):
    """Return hex color for a given point based on result ratios."""

    sum_results = num_nofaults + num_faults + num_crashes + num_resets + num_soft_bricked + num_hard_bricked # NOT including num_skipped
    # num_nofaults, num_faults, num_skipped
    num_instabilities = num_resets + num_crashes + num_soft_bricked + num_hard_bricked

    # Gray: if no data exists for that point (or all were skipped)
    if sum_results == 0:
        return "gray"

    # Green: normal operation (no faults, crashes, resets or skips)
    if (num_faults + num_resets + num_crashes + num_soft_bricked + num_hard_bricked + num_skipped) == 0:
        return "green"

    # Red: Only faults
    if num_faults > 0 and num_nofaults == 0 and num_resets == 0 and num_crashes == 0:
        return "red"

    # Yellow - Red: Some faults occured (color depending on faults / n executions)
    if num_faults > 0:
        start_color = colors.to_rgb("#cffc03")  # yellow-green start
        end_color = colors.to_rgb("#ff0000")    # red end
        denom = num_nofaults + num_resets + num_crashes + num_soft_bricked + num_hard_bricked
        ratio = num_faults / sum_results
        return colors.to_hex(mix_colors(start_color, end_color, ratio))

    # Blue: No faults, but resets or crashes (color depending on ration of (resets + crashes) / n executions)
    if num_faults == 0 and num_instabilities > 0:
        start_color = colors.to_rgb("#03fc9d")  # teal start
        end_color = colors.to_rgb("#0000ff")    # blue end
        ratio = num_instabilities / sum_results
        return colors.to_hex(mix_colors(start_color, end_color, ratio))

    return "gray"

class GlitchVisualizer:
    def __init__(self, root, json_data):
        self.root = root
        root.title("Glitch Visualizer")

        self.data = json_data
        self.positions = self.data['positions']
        self.glitch_configs = self.data['glitch_configs']
        self.num_configs = len(self.glitch_configs)
        self.current_config_index = 0
        self.current_point_index = 0

        self.last_clicked_index = None
        self._first_plot_update = True

        # Configure grid weights for resizing
        # root.grid_columnconfigure(0, weight=3)  # Left plot
        # root.grid_columnconfigure(1, weight=1)  # Sidebar
        # root.grid_rowconfigure(0, weight=1)

        # Create main PanedWindow for resizable columns
        self.main_pane = tk.PanedWindow(
            root,
            orient=tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=8,
            opaqueresize=True
        )
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # === Left Plot Area Pane ===
        self.plot_frame = tk.Frame(self.main_pane)
        self.main_pane.add(self.plot_frame, minsize=400)  # Minimum width for plot area

        # === Plot Area ===
        self.fig, self.ax = plt.subplots(figsize=(6, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)  # Changed to plot_frame
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # === Right Sidebar Pane divided into glitch_config (top) and point_info (bottom) ===
        self.sidebar_pane = PanedWindow(self.main_pane, orient=VERTICAL, bg='#f0f0f0')
        self.main_pane.add(self.sidebar_pane, minsize=200)  # Minimum width for sidebar


        # === Glitch Configuration Values ===
        self.top_info = tk.Frame(self.sidebar_pane)
        self.sidebar_pane.add(self.top_info)

        self.insert_config_navigation(self.top_info)

        glitch_parameters = json_data["glitch_configs"][self.current_config_index]

        # Treeview as Parameter Table
        self.param_tree = ttk.Treeview(
            self.top_info,
            columns=("Parameter", "Value"),
            show="headings",
            height=len(glitch_parameters)
        )

        self.param_tree.heading("Parameter", text="Parameter")
        self.param_tree.heading("Value", text="Value")
        self.param_tree.column("Parameter", anchor="w")
        self.param_tree.column("Value", anchor="w")

        # self.param_tree.pack(padx=1, pady=1, fill="x")
        self.param_tree.pack(fill="both", expand=True, padx=1, pady=1)


        # === Bottom Info (Point Details) ===
        self.bottom_info = tk.LabelFrame(self.sidebar_pane, text="Point Details")
        self.sidebar_pane.add(self.bottom_info)

        # Treeview as Point Details Table
        self.point_tree = ttk.Treeview(
            self.bottom_info,
            columns=("Value"),
            # show="headings",
            # height=6  # Enough rows for all point properties
        )
        self.point_tree.column("#0", anchor="w", width=150, minwidth=100, stretch=tk.NO)
        self.point_tree.column("Value", anchor="w", minwidth=100, stretch=tk.YES)

        self.point_tree.heading("#0", text="Property")
        self.point_tree.heading("Value", text="Value")
        self.point_tree.pack(fill="both", expand=True, padx=1, pady=1)

        # Initialize with empty data
        self.clear_point_details()

        # === Update View ===
        self.update_glitch_config_display()

    def insert_config_navigation(self, parent):
        self.control_frame = tk.Frame(parent, height=1)
        self.control_frame.pack(pady=3)

        self.control_label = tk.Label(self.control_frame, text="Glitch configuration: ")
        self.control_label.pack(side="left")
        # Decrement button
        self.decrement_btn = tk.Button(
            self.control_frame,
            text="←",
            command=self.decrement_config
        )
        self.decrement_btn.pack(side="left")
        # Number input (using Spinbox for better control)
        self.config_spinbox = tk.Spinbox(
            self.control_frame,
            from_=0,
            to=len(self.data["glitch_configs"])-1,
            width=3,
            command=self.on_config_change
        )
        self.config_spinbox.pack(side="left")
        self.config_spinbox.delete(0, "end")
        self.config_spinbox.insert(0, str(self.current_config_index))
        # Increment button
        self.increment_btn = tk.Button(
            self.control_frame,
            text="→",
            command=self.increment_config
        )
        self.increment_btn.pack(side="left")

        return self.control_frame


    # Add these methods to your class
    def increment_config(self):
        current = int(self.config_spinbox.get())
        max_val = self.num_configs - 1
        new_val = current + 1 if current < max_val else 0

        self.config_spinbox.delete(0, "end")
        self.config_spinbox.insert(0, str(new_val))
        self.on_config_change()

    def decrement_config(self):
        current = int(self.config_spinbox.get())
        max_val = self.num_configs - 1
        new_val = current - 1 if current > 0 else max_val

        self.config_spinbox.delete(0, "end")
        self.config_spinbox.insert(0, str(new_val))
        self.on_config_change()

    def on_config_change(self):
        new_index = int(self.config_spinbox.get())
        if new_index != self.current_config_index:
            self.current_config_index = new_index
            self.update_glitch_config_display()

    def update_glitch_config_display(self):
        """Update both plot and sidebar when config changes"""
        self.update_glitch_params_sidebar()
        self.update_point_details_sidebar()
        self.update_plot()

    def update_glitch_params_sidebar(self):
        """Update the sidebar with current config parameters"""
        # Clear existing rows
        for row in self.param_tree.get_children():
            self.param_tree.delete(row)

        # Get current config
        config = self.glitch_configs[self.current_config_index]

        # Insert new parameter rows
        for param, value in config.items():
            if param != 'results':  # Skip the results data
                self.param_tree.insert("", "end", values=(param, value))

    def update_plot(self):
        """Update the plot with current config data"""
        self.ax.clear()

        config = self.glitch_configs[self.current_config_index]
        results = config['results']

        # Get x,y positions
        self.positions_xy = [(x, y) for x, y, _ in self.positions]
        xs = [pos[0] for pos in self.positions]
        ys = [pos[1] for pos in self.positions]

        # Color points based on results
        colors_list = [
            classify_color(
                results["num_nofaults"][i],
                results["num_faults"][i],
                results["num_crashes"][i],
                results["num_resets"][i],
                results["num_soft_bricked"][i] if "num_soft_bricked" in results else 0,
                results["num_hard_bricked"][i] if "num_hard_bricked" in results else 0,
                results["num_skipped"][i]      if "num_skipped" in results else 0,
            ) for i in range(len(self.positions_xy))
        ]

        # Highlight points where exeutions were skipped with pink perimeter
        if "num_skipped" in results:
            edgecolors_list = [
                ("#F80BD8" if num_skipped > 0 else "black") for num_skipped in results["num_skipped"]
            ]
        else:
            edgecolors_list = "black"

        # Create scatter plot
        self.scat = self.ax.scatter(xs, ys, c=colors_list, s=120, linewidths=2, edgecolors=edgecolors_list)
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_title(f"Fault Injection Point Matrix (Config {self.current_config_index})")
        self.ax.set_aspect('equal', 'box')
        self.ax.invert_yaxis()

        # Add legend
        legend_elements = [
            Patch(facecolor='green', edgecolor='black', label='Normal operation'),
            Patch(facecolor='#ff0000', edgecolor='black', label='Faults'),
            Patch(facecolor='#0000ff', edgecolor='black', label='Resets & Crashes'),
            # Patch(facecolor='gray', edgecolor='black', label='No data')
        ]
        # self.ax.legend(handles=legend_elements, bbox_to_anchor=(1.05, 1), loc='upper left')

        self.ax.legend(
            handles=legend_elements,
            bbox_to_anchor=(0.5, -0.15),
            loc='upper center',
            ncol=3,
            borderaxespad=0.5
        )

        # Connect click event
        self.canvas.mpl_connect('pick_event', self.on_point_click)
        self.scat.set_picker(True)  # Enable picking on the scatter plot


        # Critical steps to make Tkinter respect the new layout:
        # 1. First draw the canvas to calculate sizes
        self.canvas.draw()

        if self._first_plot_update:
            # 2. Adjust the figure size to include legend space
            fig_width, fig_height = self.fig.get_size_inches()
            legend_height = 0.4  # Inches to allocate for legend
            self.fig.set_size_inches(fig_width, fig_height + legend_height)

            # 3. Adjust subplot parameters to make room
            self.fig.subplots_adjust(bottom=0.25)  # Increase bottom margin

            # 4. Force Tkinter to recalculate layout
            self.canvas.get_tk_widget().update_idletasks()
            self.root.update_idletasks()

            # 5. Redraw everything
            self.canvas.draw_idle()
            self._first_plot_update = False

    def clear_point_details(self):
        """Clear the point details table"""
        for row in self.point_tree.get_children():
            self.point_tree.delete(row)
        self.point_tree.insert("", "end", text="No point", values=("selected"))

    def update_point_details_sidebar(self):
        """Update the point details table with information for the given point"""
        # Clear existing rows
        for row in self.point_tree.get_children():
            self.point_tree.delete(row)

        config = self.glitch_configs[self.current_config_index]
        results = config['results']
        position = self.positions[self.current_point_index]

        # Insert point position:
        self._insert_point_param("", "Position", f"({position[0]}, {position[1]})")

        # Insert all of the result data
        for result_type, result in results.items():
            if result_type.startswith("num_"):
                self._insert_point_param("", result_type, result[self.current_point_index])
            else:
                extradata = [extradata["data"] for extradata in result if extradata["position_index"] == self.current_point_index]
                if len(extradata) == 1:
                    extradata = extradata[0]
                self._insert_point_param("", result_type, extradata)

        self.point_tree.bind('<Control-c>', self.copy_fault_data)


    def _insert_point_param(self, parent, key, value, tag=None):
        """
        Recursively insert a key/value into the Treeview.
        If value is a dict, create child items for each key.
        If value is a list, create child items for each element.
        Otherwise, insert as a leaf node.
        """
        if isinstance(value, dict):
            # Parent node for this dict
            node = self.point_tree.insert(parent, "end", text=str(key), values=("dict",), open=True, tags=(tag,) if tag else ())
            for k, v in value.items():
                self._insert_point_param(node, k, v, tag=tag)
        elif isinstance(value, list):
            # Parent node for list
            node = self.point_tree.insert(parent, "end", text=str(key), values=(f"list[{len(value)}]",), open=True, tags=(tag,) if tag else ())
            for i, item in enumerate(value):
                self._insert_point_param(node, f"{i+1}", item, tag=tag)
        else:
            # Leaf node
            node = self.point_tree.insert(parent, "end", text=str(key), values=(str(value),), tags=(tag,) if tag else ())

        return node


    def copy_fault_data(self, event):
        """Copy selected fault data to clipboard"""
        selected = self.point_tree.selection()
        if not selected:
            return

        item = selected[0]
        # Get the full value directly from the item's values
        values = self.point_tree.item(item, 'values')
        if values:
            self.root.clipboard_clear()
            self.root.clipboard_append(values[0])
            return "break"  # Prevent default handling



    def on_point_click(self, event):
        """Handle when a point is clicked on the plot"""
        if not hasattr(event, 'ind'):
            return  # Not a valid pick event

        point_index = event.ind[0]  # Get the index of the clicked point
        self.last_clicked_index = point_index

        self.current_point_index = point_index
        self.update_point_details_sidebar()

def main():
    json_path = DEFAULT_JSON_PATH
    if len(sys.argv) > 1:
        json_path = sys.argv[1]

    with open(json_path, 'r') as f:
        data = json.load(f)

    root = tk.Tk()
    # root.attributes("-fullscreen", True)  # substitute `Tk` for whatever your `Tk()` object is called

    # Set up proper window closing behavior
    def on_closing():
        root.quit()  # Ends mainloop()
        root.destroy()  # Destroys all widgets
        plt.close('all')  # Closes any matplotlib figures

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Handle Ctrl+C in terminal
    def sigint_handler(signum, frame):
        on_closing()
        sys.exit(1)

    signal.signal(signal.SIGINT, sigint_handler)

    # Display GlitchVisualizer App
    app = GlitchVisualizer(root, data)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        on_closing()

if __name__ == '__main__':
    main()
