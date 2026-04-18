"""
UI Control Panel for Autonomous Delivery System
Provides buttons and controls for managing deliveries
"""

from controller import Supervisor, Display
import math

class DeliveryControlPanel:
    def __init__(self, robot):
        self.robot = robot
        self.display = None
        self.button_width = 120
        self.button_height = 40
        self.panel_width = 400
        self.panel_height = 400
        self.start_x = 10
        self.start_y = 10
        
        # Try to get display device
        try:
            self.display = self.robot.getDevice("display")
            print("[UI] Display device initialized")
        except:
            print("[UI] Display device not available")
        
        # Button states
        self.buttons = {
            "START_ALL": {"x": 20, "y": 20, "w": 150, "h": 40, "text": "Start All Deliveries"},
            "START_A": {"x": 20, "y": 70, "w": 150, "h": 30, "text": "Deliver to A"},
            "START_B": {"x": 20, "y": 105, "w": 150, "h": 30, "text": "Deliver to B"},
            "START_C": {"x": 20, "y": 140, "w": 150, "h": 30, "text": "Deliver to C"},
            "START_D": {"x": 20, "y": 175, "w": 150, "h": 30, "text": "Deliver to D"},
            "STOP": {"x": 20, "y": 220, "w": 150, "h": 40, "text": "STOP"},
            "STATUS": {"x": 20, "y": 270, "w": 350, "h": 120, "text": "STATUS"},
        }
    
    def draw_button(self, button_id, button, is_pressed=False):
        """Draw a button on the display"""
        if not self.display:
            return
        
        # Button background
        if is_pressed:
            self.display.setColor(0xFF0000)  # Red when pressed
        else:
            self.display.setColor(0x0099FF)  # Blue
        
        self.display.fillRectangle(button["x"], button["y"], button["w"], button["h"])
        
        # Border
        self.display.setColor(0x000000)  # Black
        self.display.drawRectangle(button["x"], button["y"], button["w"], button["h"])
        
        # Text
        self.display.setColor(0xFFFFFF)  # White
        text_x = button["x"] + 5
        text_y = button["y"] + button["h"] // 2 - 5
        self.display.drawText(button["text"], text_x, text_y)
    
    def draw_panel(self, delivery_state):
        """Render the entire control panel"""
        if not self.display:
            return
        
        # Clear display
        self.display.setColor(0x333333)  # Dark gray background
        self.display.fillRectangle(0, 0, 400, 400)
        
        # Draw buttons
        for button_id, button in self.buttons.items():
            self.draw_button(button_id, button)
        
        # Draw status info
        self.display.setColor(0xFFFFFF)
        self.display.drawText(f"State: {delivery_state['state']}", 180, 280)
        self.display.drawText(f"Battery: {delivery_state['battery']:.1f}%", 180, 300)
        self.display.drawText(f"Target: {delivery_state['target']}", 180, 320)
        self.display.drawText(f"Delivered: {delivery_state['delivered']}", 180, 340)
    
    def get_display_size(self):
        """Get display resolution"""
        if self.display:
            return self.display.getWidth(), self.display.getHeight()
        return 400, 400
    
    def check_button_click(self, mouse_x, mouse_y, button_id):
        """Check if a button was clicked"""
        if button_id not in self.buttons:
            return False
        
        button = self.buttons[button_id]
        return (button["x"] <= mouse_x <= button["x"] + button["w"] and
                button["y"] <= mouse_y <= button["y"] + button["h"])


class SimulationInterface:
    """Main interface for simulation control"""
    
    def __init__(self, robot, delivery_system):
        self.robot = robot
        self.delivery = delivery_system
        self.control_panel = DeliveryControlPanel(robot)
        self.keyboard = robot.getKeyboard()
        self.keyboard.enable(16)  # Enable keyboard input
        
    def handle_keyboard_input(self):
        """Handle keyboard commands for delivery control"""
        key = self.keyboard.getKey()
        
        if key == ord('S'):  # Start all deliveries
            if self.delivery.state == "IDLE":
                print("\n[INPUT] Starting all deliveries (S key)")
                self.delivery.start_delivery_route()
                return True
        
        elif key == ord('A'):  # Start delivery to A only
            if self.delivery.state == "IDLE":
                print("\n[INPUT] Starting delivery to HOUSE_A (A key)")
                self.delivery.start_delivery_route(["HOUSE_A"])
                return True
        
        elif key == ord('B'):  # Start delivery to B
            if self.delivery.state == "IDLE":
                print("\n[INPUT] Starting delivery to HOUSE_B (B key)")
                self.delivery.start_delivery_route(["HOUSE_B"])
                return True
        
        elif key == ord('C'):  # Start delivery to C
            if self.delivery.state == "IDLE":
                print("\n[INPUT] Starting delivery to HOUSE_C (C key)")
                self.delivery.start_delivery_route(["HOUSE_C"])
                return True
        
        elif key == ord('D'):  # Start delivery to D
            if self.delivery.state == "IDLE":
                print("\n[INPUT] Starting delivery to HOUSE_D (D key)")
                self.delivery.start_delivery_route(["HOUSE_D"])
                return True
        
        elif key == ord('Q'):  # Quit/Stop
            print("\n[INPUT] STOP command (Q key) - Returning to HOME")
            self.delivery.state = "RETURNING"
            self.delivery.current_target = "HOME"
            return True
        
        elif key == ord('P'):  # Print status
            self.delivery.print_status()
            return True
        
        return False
    
    def render_ui(self):
        """Render the UI on display"""
        delivery_state = {
            "state": self.delivery.state,
            "battery": self.delivery.battery_level,
            "target": self.delivery.current_target or "None",
            "delivered": self.delivery.delivered_count,
        }
        
        self.control_panel.draw_panel(delivery_state)


def print_control_help():
    """Print keyboard control instructions"""
    print("\n" + "="*60)
    print("KEYBOARD CONTROLS - DELIVERY SYSTEM")
    print("="*60)
    print("  S  - Start deliveries to ALL houses")
    print("  A  - Deliver to HOUSE_A only")
    print("  B  - Deliver to HOUSE_B only")
    print("  C  - Deliver to HOUSE_C only")
    print("  D  - Deliver to HOUSE_D only")
    print("  Q  - STOP and return to HOME")
    print("  P  - Print detailed status")
    print("="*60 + "\n")
