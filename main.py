import sys
import tkinter as tk
from gui import ConfigManager, DashboardApp
from macro_core import AutoFishingEngine

def main():
    config_manager = ConfigManager()
    engine = AutoFishingEngine(config_manager)

    root = tk.Tk()
    app = DashboardApp(root, engine, config_manager)

    def on_closing():
        engine.stop()
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
