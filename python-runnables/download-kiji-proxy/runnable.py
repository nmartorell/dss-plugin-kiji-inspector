import os

from dataiku.runnables import Runnable
from dataiku.runnables import ResultTable

class MyRunnable(Runnable):
    """The base interface for a Python runnable"""

    def __init__(self, project_key, config, plugin_config):
        """
        :param project_key: the project in which the runnable executes
        :param config: the dict of the configuration of the object
        :param plugin_config: contains the plugin settings
        """
        self.project_key = project_key
        self.config = config
        self.plugin_config = plugin_config
        
    def get_progress_target(self):
        """
        If the runnable will return some progress info, have this function return a tuple of 
        (target, unit) where unit is one of: SIZE, FILES, RECORDS, NONE
        """
        return None

    def run(self, progress_callback):
        """
        Do stuff here. Can return a string or raise an exception.
        The progress_callback is a function expecting 1 value: current progress
        """
        resource_folder = os.getenv("DKU_CUSTOM_RESOURCE_FOLDER")

        result = ResultTable()
        result.set_name("download_kiji_proxy_environment")
        result.set_header("Runnable environment")
        result.add_column("variable", "Variable")
        result.add_column("value", "Value")
        result.add_record({
            "variable": "DKU_CUSTOM_RESOURCE_FOLDER",
            "value": resource_folder or ""
        })
        return result
        
