import os
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget
from managers.vfs_manager import VFSManager


class ImageManager(QThread):
    operationCompleted = Signal(bool, str)
    showMessage = Signal(str, str)
    imageLoaded = Signal(object)  # New signal to pass VFS manager to UI

    def __init__(self):
        super().__init__()
        self.operation = None
        self.image_path = None
        self.file_name = None
        self.vfs_manager = VFSManager()

    def run(self):
        if self.operation == 'load' and self.image_path:
            try:
                self.vfs_manager.open_image(self.image_path)
                
                # Try to get volumes first
                volumes = self.vfs_manager.get_volumes()
                
                if volumes:
                    # If there are volumes, open the first one
                    self.vfs_manager.get_root_filesystem(volumes[0])
                    self.operationCompleted.emit(True, f"Image {self.file_name} loaded successfully with {len(volumes)} volume(s).")
                else:
                    # If no volumes, try direct filesystem access
                    self.vfs_manager.get_root_filesystem()
                    self.operationCompleted.emit(True, f"Image {self.file_name} loaded successfully.")
                
                # Emit the VFS manager so the UI can use it
                self.imageLoaded.emit(self.vfs_manager)
            except Exception as e:
                self.operationCompleted.emit(False, f"Failed to load the image. Error: {e}")
        elif self.operation == 'unload':
            try:
                self.vfs_manager.close()
                self.operationCompleted.emit(True, "Image was unloaded successfully.")
            except Exception as e:
                self.operationCompleted.emit(False, f"Failed to unload the image. Error: {e}")

    def unload_image(self):
        """Close the currently opened image."""
        self.operation = 'unload'
        self.start()

    def _is_valid_image(self, image_path):
        """Check if file has a valid disk image extension."""
        valid_extensions = ['.e01', '.dd', '.dd.gz', '.aff4', '.vhd', '.vdi', '.xva', '.vmdk', '.ova', '.qcow', '.qcow2']
        
        # Check for .dd.gz first (double extension)
        if image_path.lower().endswith('.dd.gz'):
            return True
        
        # Check standard extensions
        file_extension = os.path.splitext(image_path)[1].lower()
        return file_extension in valid_extensions

    def load_image(self):
        """Open an image after prompting the user to select one."""
        supported_formats = (
            "EWF Files (*.E01);;Raw Files (*.dd *.dd.gz);;AFF4 Files (*.aff4);;"
            "VHD Files (*.vhd);;VDI Files (*.vdi);;XVA Files (*.xva);;"
            "VMDK Files (*.vmdk);;OVA Files (*.ova);;QCOW Files (*.qcow *.qcow2);;All Files (*)"
        )

        while True:
            image_path, _ = QFileDialog.getOpenFileName(QWidget(None), "Select Disk Image", "", supported_formats)

            if not image_path:
                return

            if self._is_valid_image(image_path):
                break
            else:
                QMessageBox.warning(QWidget(None), "Invalid File Type", "The selected file is not a valid disk image.")

        self.image_path = os.path.normpath(image_path)
        self.file_name = os.path.basename(self.image_path)
        self.operation = 'load'
        self.start()
