import os
from dfvfs.lib import definitions
from dfvfs.resolver import resolver
from dfvfs.path import factory as path_spec_factory
from dfvfs.volume import factory as volume_system_factory


class VFSManager:
    """Manage virtual file system access to disk images using dfvfs."""
    
    def __init__(self):
        self.image_path = None
        self.file_name = None
        self.root_fs_object = None
        self.path_spec = None
        self.volume_system = None
    
    def _get_image_path_spec(self, image_path):
        """
        Get the proper path spec for an image file, detecting format and compression.
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            path_spec: The appropriate dfvfs path specification
        """
        # Start with OS path
        os_path_spec = path_spec_factory.Factory.NewPathSpec(
            definitions.TYPE_INDICATOR_OS,
            location=image_path
        )
        
        # For .E01 files, use EWF format
        if image_path.lower().endswith('.e01'):
            return path_spec_factory.Factory.NewPathSpec(
                definitions.TYPE_INDICATOR_EWF,
                parent=os_path_spec
            )
        
        # For other formats, we'll handle compression separately
        path_spec = os_path_spec
        
        # Handle gzip compression - wrap in GZIP (not COMPRESSED_STREAM)
        if image_path.lower().endswith('.gz'):
            path_spec = path_spec_factory.Factory.NewPathSpec(
                definitions.TYPE_INDICATOR_GZIP,
                parent=path_spec
            )
        
        # For .qcow, .qcow2, .vhd, .vmdk formats
        if image_path.lower().endswith(('.qcow', '.qcow2')):
            path_spec = path_spec_factory.Factory.NewPathSpec(
                definitions.TYPE_INDICATOR_QCOW,
                parent=path_spec
            )
        elif image_path.lower().endswith('.vhd'):
            path_spec = path_spec_factory.Factory.NewPathSpec(
                definitions.TYPE_INDICATOR_VHDI,
                parent=path_spec
            )
        elif image_path.lower().endswith('.vmdk'):
            path_spec = path_spec_factory.Factory.NewPathSpec(
                definitions.TYPE_INDICATOR_VMDK,
                parent=path_spec
            )
        
        # For .dd, .dd.gz, .raw, .img, etc., return the path spec as-is
        # (either OS or GZIP-wrapped OS) and let the volume system detect
        return path_spec
    
    def open_image(self, image_path):
        """
        Open a disk image without mounting it.
        
        Args:
            image_path (str): Path to the disk image
            
        Raises:
            Exception: If image cannot be opened
        """
        try:
            self.image_path = os.path.normpath(image_path)
            self.file_name = os.path.basename(self.image_path)
            
            # Get the proper path spec for this image
            self.path_spec = self._get_image_path_spec(self.image_path)
            
            # Try to open volume system to detect partitions
            try:
                self.volume_system = volume_system_factory.Factory.NewVolumeSystem(self.path_spec)
                if self.volume_system and hasattr(self.volume_system, 'volumes'):
                    # Check if we actually have volumes
                    vol_list = list(self.volume_system.volumes)
                    if not vol_list:
                        self.volume_system = None
            except Exception:
                # No partitions, might be a raw filesystem
                self.volume_system = None
            
            return True
        except Exception as e:
            raise Exception(f"Failed to open image: {str(e)}")
    
    def get_volumes(self):
        """
        Get all volumes/partitions from the image.
        
        Returns:
            list: List of volume objects, or empty list if no partition table
        """
        try:
            if not self.volume_system:
                return []
            
            volumes = []
            for volume in self.volume_system.volumes:
                volumes.append(volume)
            return volumes
        except Exception as e:
            return []
    
    def get_root_filesystem(self, volume=None):
        """
        Get the root filesystem object from a volume or the image itself.
        
        Args:
            volume: Optional volume object. If None, tries to open image directly.
        
        Returns:
            VFS file entry object or None if not found
            
        Raises:
            Exception: If filesystem cannot be accessed
        """
        try:
            if volume:
                # Open filesystem from a specific volume
                path_spec = volume.path_spec
                file_entry = resolver.Resolver.OpenFileEntry(path_spec)
            else:
                # If we have a volume system, we need to get the first volume
                if self.volume_system:
                    volumes = list(self.volume_system.volumes)
                    if volumes:
                        path_spec = volumes[0].path_spec
                        file_entry = resolver.Resolver.OpenFileEntry(path_spec)
                    else:
                        raise Exception("Volume system exists but has no volumes")
                else:
                    # No volume system, try to use TSK to detect filesystem
                    try:
                        # Try with TSK partition table detection
                        tsk_path_spec = path_spec_factory.Factory.NewPathSpec(
                            definitions.TYPE_INDICATOR_TSK_PARTITION,
                            parent=self.path_spec
                        )
                        file_entry = resolver.Resolver.OpenFileEntry(tsk_path_spec)
                    except:
                        # If TSK fails, try directly with the path spec
                        file_entry = resolver.Resolver.OpenFileEntry(self.path_spec)
            
            if file_entry:
                self.root_fs_object = file_entry
            else:
                raise Exception(f"Could not open file entry")
            
            return self.root_fs_object
        except Exception as e:
            raise Exception(f"Failed to get root filesystem: {str(e)}")
    
    def list_files(self, path='/'):
        """
        List files in a directory within the image.
        
        Args:
            path (str): Directory path to list
            
        Returns:
            list: List of file entries
            
        Raises:
            Exception: If files cannot be listed
        """
        try:
            if not self.root_fs_object:
                self.get_root_filesystem()
            
            files = []
            
            # List entries in root or specified directory
            if self.root_fs_object.IsDirectory():
                for sub_file_entry in self.root_fs_object.ListFileEntries():
                    files.append({
                        'name': sub_file_entry.name,
                        'path': sub_file_entry.path_spec.location,
                        'is_directory': sub_file_entry.IsDirectory(),
                        'size': sub_file_entry.GetSize() if not sub_file_entry.IsDirectory() else 0
                    })
            
            return files
        except Exception as e:
            raise Exception(f"Failed to list files: {str(e)}")
    
    def list_directory_entries(self, file_entry):
        """
        List all entries in a directory file entry.
        
        Args:
            file_entry: A dfvfs file entry object representing a directory
            
        Returns:
            list: List of file entries with metadata
        """
        try:
            entries = []
            
            if file_entry and file_entry.IsDirectory():
                for sub_entry in file_entry.ListFileEntries():
                    entry_info = {
                        'name': sub_entry.name,
                        'is_directory': sub_entry.IsDirectory(),
                        'size': sub_entry.GetSize() if not sub_entry.IsDirectory() else 0,
                        'file_entry': sub_entry
                    }
                    
                    # Try to get timestamps
                    try:
                        if hasattr(sub_entry, 'GetAccessTime'):
                            entry_info['accessed'] = sub_entry.GetAccessTime()
                        if hasattr(sub_entry, 'GetChangeTime'):
                            entry_info['changed'] = sub_entry.GetChangeTime()
                        if hasattr(sub_entry, 'GetCreationTime'):
                            entry_info['created'] = sub_entry.GetCreationTime()
                        if hasattr(sub_entry, 'GetModificationTime'):
                            entry_info['modified'] = sub_entry.GetModificationTime()
                    except:
                        pass
                    
                    entries.append(entry_info)
            
            return entries
        except Exception as e:
            raise Exception(f"Failed to list directory entries: {str(e)}")
    
    def extract_file(self, source_path, destination_path):
        """
        Extract a file from the image to the destination.
        
        Args:
            source_path (str): Path to file within the image
            destination_path (str): Where to save the extracted file
            
        Returns:
            bool: True if successful
            
        Raises:
            Exception: If file cannot be extracted
        """
        try:
            if not self.root_fs_object:
                self.get_root_filesystem()
            
            # Ensure destination directory exists
            dest_dir = os.path.dirname(destination_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            
            # Read and write the file
            with open(destination_path, 'wb') as dest_file:
                file_object = self.root_fs_object.GetFileObject()
                if file_object:
                    dest_file.write(file_object.read())
                    file_object.close()
            
            return True
        except Exception as e:
            raise Exception(f"Failed to extract file: {str(e)}")
    
    def close(self):
        """Close the image and clean up resources."""
        try:
            if self.root_fs_object:
                self.root_fs_object.Close()
                self.root_fs_object = None
            self.path_spec = None
        except Exception as e:
            raise Exception(f"Failed to close image: {str(e)}")