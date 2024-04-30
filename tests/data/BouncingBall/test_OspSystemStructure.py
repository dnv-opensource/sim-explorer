import os
from libcosimpy.CosimExecution import CosimExecution

sim = CosimExecution.from_osp_config_file( str( os.path.join( os.path.abspath('.'), 'OspSystemStructure.xml')))
print( sim)
