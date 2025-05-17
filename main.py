import os
from kivy.utils import platform
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.camera import Camera
from kivymd.app import MDApp
import sqlite3
from datetime import datetime

# Android permissions
if platform == 'android':
    from android.permissions import request_permissions, Permission
    from android.storage import app_storage_path
    request_permissions([Permission.CAMERA, Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
else:
    from kivy.config import Config
    Config.set('graphics', 'width', '400')
    Config.set('graphics', 'height', '600')

Window.size = (400, 600) if platform != 'android' else Window.size


class LoadingPopup(BoxLayout):
    pass


class SimpleCameraWidget(Image):
    def __init__(self, **kwargs):
        super(SimpleCameraWidget, self).__init__(**kwargs)
        self.capture = None
        self.fps = 30
        self.capture_event = None

    def start_camera(self):
        try:
            import cv2
            self.capture = cv2.VideoCapture(0)
            if not self.capture.isOpened():
                print("Camera failed to open")
                return False
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture_event = Clock.schedule_interval(self.update_frame, 1.0 / self.fps)
            return True
        except Exception as e:
            print(f"OpenCV error: {str(e)}")
            return False

    def update_frame(self, dt):
        ret, frame = self.capture.read()
        if ret:
            import cv2
            buf = cv2.flip(frame, 0).tobytes()
            texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='bgr')
            texture.blit_buffer(buf, colorfmt='bgr', bufferfmt='ubyte')
            self.texture = texture

    def stop_camera(self):
        if self.capture_event:
            self.capture_event.cancel()
        if self.capture:
            self.capture.release()


class KivyCameraWidget(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.camera = Camera(play=False)
        self.camera.resolution = (640, 480)
        self.add_widget(self.camera)

    def start_camera(self):
        self.camera.play = True
        return True

    def stop_camera(self):
        self.camera.play = False

    def capture_photo(self):
        # Fake capture for now; can't access image buffer directly from Kivy camera
        return None  # You would need to extend functionality to grab texture and save it


class HomeScreen(Screen):
    def show_permission_popup(self):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text="Allow camera access?"))

        btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        allow_btn = Button(text="Allow", on_press=self.grant_access)
        deny_btn = Button(text="Deny", on_press=self.popup_dismiss)
        btn_layout.add_widget(allow_btn)
        btn_layout.add_widget(deny_btn)
        content.add_widget(btn_layout)

        self.popup = Popup(title="Camera Permission", content=content, size_hint=(0.8, 0.4))
        self.popup.open()

    def grant_access(self, instance=None):
        self.popup.dismiss()
        loading_content = LoadingPopup()
        self.loader_popup = Popup(title="Please wait...", content=loading_content,
                                  size_hint=(None, None), size=(300, 250), auto_dismiss=False)
        self.loader_popup.open()
        Clock.schedule_once(self.check_camera_ready, 0.5)

    def check_camera_ready(self, dt):
        camera_screen = self.manager.get_screen('camera')
        if camera_screen.camera_widget is None:
            camera_screen.on_pre_enter()
        if camera_screen.camera_widget and camera_screen.camera_widget.start_camera():
            self.loader_popup.dismiss()
            self.manager.current = 'camera'
        else:
            Clock.schedule_once(self.check_camera_ready, 0.5)

    def popup_dismiss(self, instance=None):
        if hasattr(self, 'popup') and self.popup:
            self.popup.dismiss()


class CameraScreen(Screen):
    camera_placeholder = ObjectProperty(None)
    name_input = ObjectProperty(None)
    status_label = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.camera_widget = None
        self.image_folder = self.get_app_storage_path()
        os.makedirs(self.image_folder, exist_ok=True)

    def get_app_storage_path(self):
        if platform == 'android':
            return app_storage_path()
        return os.path.join(os.getcwd(), 'captured_images')

    def get_database_path(self):
        if platform == 'android':
            return os.path.join(app_storage_path(), 'attendance.db')
        return 'attendance.db'

    def on_pre_enter(self, *args):
        if not self.camera_widget:
            if platform == 'android':
                self.camera_widget = KivyCameraWidget()
            else:
                self.camera_widget = SimpleCameraWidget()
            self.ids.camera_placeholder.add_widget(self.camera_widget)

    def on_enter(self, *args):
        if self.camera_widget:
            self.camera_widget.start_camera()

    def on_pre_leave(self, *args):
        if self.camera_widget:
            self.camera_widget.stop_camera()
            self.ids.camera_placeholder.remove_widget(self.camera_widget)
            self.camera_widget = None

    def capture_image(self):
        name = self.ids.name_input.text.strip()
        if not name:
            self.ids.status_label.text = "Enter name first!"
            return

        frame = self.camera_widget.capture_photo()
        if frame is not None:
            from cv2 import imwrite
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"captured_{name}_{timestamp}.jpg"
            file_path = os.path.join(self.image_folder, filename)
            imwrite(file_path, frame)
            self.save_to_db(name, timestamp, file_path)
            self.ids.status_label.text = f"Saved {filename}!"
            Clock.schedule_once(lambda dt: self.set_current('home'), 2)
        else:
            self.ids.status_label.text = "Camera capture not supported on this platform."

    def go_back(self):
        self.manager.current = 'home'

    def set_current(self, screen_name):
        self.manager.current = screen_name

    def save_to_db(self, name, timestamp, file_path):
        db_path = self.get_database_path()
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS attendance
                        (id INTEGER PRIMARY KEY, name TEXT, timestamp TEXT, image_path TEXT)''')
            c.execute("INSERT INTO attendance (name, timestamp, image_path) VALUES (?,?,?)",
                      (name, timestamp, file_path))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Database error: {str(e)}")
        finally:
            conn.close()


class AttendanceApp(MDApp):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(CameraScreen(name='camera'))
        return sm


if __name__ == '__main__':
    AttendanceApp().run()
