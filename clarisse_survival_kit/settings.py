import logging
import collections

# File handling. If multiple extensions exist in the folder the most left extension will be picked.
IMAGE_FORMATS = ('tx', 'exr', 'hdr', 'tif', 'tiff', 'tga', 'png', 'jpg', 'jpeg')
FILENAME_MATCH_TEMPLATE = {'diffuse': r'(?:_Diffuse|_Albedo|_baseColor|_color|albedo|^diffuse$|^color$)',
                           'specular': r'(?:_Specular|_spec$|_Reflection|^specular$|^reflection$)',
                           'roughness': r'(?:_Roughness|^roughness$)',
                           'refraction': r'(?:_refraction|^refraction$)',
                           'gloss': r'(?:_Gloss|_glossiness|^glossiness$)',
                           'normal': r'(?:_Normal|_NormalBump$|^normal$)',
                           'bump': r'(?:_bump|^bump$)',
                           'normal_lods': r'_Normal_LOD[0-9]$',
                           'opacity': r'(?:_Opacity|_transparency|^opacity$|^transparency$)',
                           'translucency': r'_Translucency',
                           'emissive': r'(?:_Emissive|^emissive$|^luminance$|^luminosity$)',
                           'ior': r'(?:_ior|^ior$)',
                           'f0': r'(?:_f0|^f0$)',
                           'displacement': r'(?:_Displacement|_height|^displacement$|^height$)',
                           'ao': r'(?:_ao|^ao$|_occlusion)',
                           'preview': r'(?:_preview|^preview$|_render)'}

MEGASCANS_SRGB_TEXTURES = ['diffuse', 'translucency']
SUBSTANCE_SRGB_TEXTURES = ['diffuse', 'specular', 'emissive', 'translucency']

# Default material variables
MATERIAL_SUFFIX = "_mtl"
PREVIEW_MATERIAL_SUFFIX = "_preview" + MATERIAL_SUFFIX
MATERIAL_LOD_SUFFIX = "_lod%i" + MATERIAL_SUFFIX
DIFFUSE_SUFFIX = "_diffuse_tx"
SPECULAR_COLOR_SUFFIX = "_specular_tx"
SPECULAR_ROUGHNESS_SUFFIX = "_roughness_tx"
OPACITY_SUFFIX = "_opacity_tx"
REFRACTION_SUFFIX = "_refraction_tx"
TRANSLUCENCY_SUFFIX = "_translucency_tx"
EMISSIVE_SUFFIX = "_emissive_tx"
IOR_SUFFIX = "_ior_tx"
IOR_DIVIDE_SUFFIX = "_ior_divide_tx"
F0_SUFFIX = "_f0_tx"
METALLIC_SUFFIX = "_metallic_tx"
BUMP_SUFFIX = "_bump_tx"
BUMP_MAP_SUFFIX = "_bump_map"
NORMAL_SUFFIX = "_normal_tx"
NORMAL_MAP_SUFFIX = "_normal_map"
NORMAL_LOD_SUFFIX = '_normal_lod%i_tx'
NORMAL_MAP_LOD_SUFFIX = '_normal_lod%i_map'
TRIPLANAR_SUFFIX = "_triplanar"
DISPLACEMENT_SUFFIX = "_displacement_tx"
DISPLACEMENT_MAP_SUFFIX = "_displacement_map"
OCCLUSION_SUFFIX = "_ao_tx"
OCCLUSION_BLEND_SUFFIX = "ao_blend_tx"
SINGLE_CHANNEL_SUFFIX = "_single_channel"
PREVIEW_SUFFIX = "_preview"
DEFAULT_DISPLACEMENT_HEIGHT = .1
DEFAULT_PLANT_DISPLACEMENT_HEIGHT = 0.01
DEFAULT_UV_SCALE = (1, 1)
DEFAULT_IOR = 1.5
DEFAULT_SPECULAR_STRENGTH = .2
DEFAULT_AO_BLEND_STRENGTH = .85

SUFFIXES = {
    'diffuse': DIFFUSE_SUFFIX,
    'specular': SPECULAR_COLOR_SUFFIX,
    'roughness': SPECULAR_ROUGHNESS_SUFFIX,
    'opacity': OPACITY_SUFFIX,
    'refraction': REFRACTION_SUFFIX,
    'translucency': TRANSLUCENCY_SUFFIX,
    'emissive': EMISSIVE_SUFFIX,
    'ior': IOR_SUFFIX,
    'ior_divide': IOR_DIVIDE_SUFFIX,
    'f0': F0_SUFFIX,
    'metallic': METALLIC_SUFFIX,
    'bump': BUMP_SUFFIX,
    'bump_map': BUMP_MAP_SUFFIX,
    'normal': NORMAL_SUFFIX,
    'normal_map': NORMAL_MAP_SUFFIX,
    'displacement': DISPLACEMENT_SUFFIX,
    'displacement_map': DISPLACEMENT_MAP_SUFFIX,
    'ao': OCCLUSION_SUFFIX,
    'ao_blend': OCCLUSION_BLEND_SUFFIX,
    'preview': PREVIEW_SUFFIX
}

TEXTURE_CONTEXTS = {
    'diffuse': ['diffuse', 'ao', 'ao_blend'],
    'specular': ['specular'],
    'roughness': ['roughness', 'gloss'],
    'refraction': ['refraction'],
    'ior': ['ior', 'ior_divide', 'f0', 'metallic'],
    'displacement': ['displacement'],
    'normal': ['normal', 'normal_map'],
    'bump': ['bump', 'bump_map'],
    'translucency': ['translucency'],
    'emissive': ['emissive']
}

TEXTURE_SETTINGS = collections.OrderedDict()
TEXTURE_SETTINGS['diffuse'] = {'single_channel': False, 'suffix': DIFFUSE_SUFFIX,
                               'connection': '.diffuse_front_color'}
TEXTURE_SETTINGS['ao'] = {'single_channel': True, 'suffix': OCCLUSION_SUFFIX,
                          'connection': '.diffuse_front_color'}
TEXTURE_SETTINGS['specular'] = {'single_channel': False, 'suffix': SPECULAR_COLOR_SUFFIX,
                                'connection': '.specular_1_color'}
TEXTURE_SETTINGS['roughness'] = {'single_channel': True, 'suffix': SPECULAR_ROUGHNESS_SUFFIX,
                                 'connection': '.specular_1_roughness'}
TEXTURE_SETTINGS['gloss'] = {'single_channel': True, 'suffix': SPECULAR_ROUGHNESS_SUFFIX,
                             'connection': '.specular_1_roughness', 'invert': True}
TEXTURE_SETTINGS['refraction'] = {'single_channel': False, 'suffix': REFRACTION_SUFFIX,
                                  'connection': '.transmission_color'}
TEXTURE_SETTINGS['ior'] = {'single_channel': False, 'suffix': IOR_SUFFIX,
                           'connection': '.specular_1_index_of_refraction'}
TEXTURE_SETTINGS['displacement'] = {'single_channel': True, 'suffix': DISPLACEMENT_SUFFIX}
TEXTURE_SETTINGS['normal'] = {'single_channel': False, 'suffix': NORMAL_SUFFIX}
TEXTURE_SETTINGS['bump'] = {'single_channel': True, 'suffix': BUMP_SUFFIX}
TEXTURE_SETTINGS['translucency'] = {'single_channel': False, 'suffix': TRANSLUCENCY_SUFFIX,
                            'connection': '.diffuse_back_color'}
TEXTURE_SETTINGS['emissive'] = {'single_channel': False, 'suffix': EMISSIVE_SUFFIX,
                                'connection': '.emission_color'}

# Other Suffixes & Variables
BLUR_SUFFIX = "_blur"
DEFAULT_BLUR_QUALITY = 4
MESH_LOD_DISPLACEMENT_LEVELS = [0, 1]
ATLAS_CTX = "atlas"
BILLBOARD_CTX = "billboard"
ATLAS_LOD_DISPLACEMENT_LEVELS = [0]
SHADING_LAYER_SUFFIX = "_shading_layer"
GROUP_SUFFIX = "_grp"
MEGASCANS_LIBRARY_CATEGORY_PREFIX = "megascans_"
LIBRARY_MIXER_CTX = "mixer"
IMPORTER_PATH_DELIMITER = "|"
DECIMATE_SUFFIX = "_decimate"
POINTCLOUD_SUFFIX = "_pc"

# Diffuse Tint variables
DIFFUSE_TINT_SUFFIX = "_tint_tx"
DEFAULT_TINT_STRENGTH = 0.5
DEFAULT_TINT_COLOR = (156, 126, 82)

# Moisture variables
MOISTURE_DIFFUSE_BLEND_SUFFIX = "_moisture_diffuse_blend_tx"
MOISTURE_SPECULAR_BLEND_SUFFIX = "_moisture_specular_blend_tx"
MOISTURE_ROUGHNESS_BLEND_SUFFIX = "_moisture_roughness_blend_tx"
MOISTURE_IOR_BLEND_SUFFIX = "_moisture_ior_blend_tx"
MOISTURE_DEFAULT_IOR = 2
MOISTURE_DEFAULT_DIFFUSE_MULTIPLIER = 0.33
MOISTURE_DEFAULT_SPECULAR_MULTIPLIER = .5
MOISTURE_DEFAULT_ROUGHNESS_MULTIPLIER = .1

# Material blend variables
MIX_SUFFIX = "_mix"
MIX_SELECTORS_NAME = "selectors"
DISPLACEMENT_BLEND_OFFSET_SUFFIX = "_displacement_blend_offset_tx"
DISPLACEMENT_OFFSET_SUFFIX = "_displacement_offset_tx"
DISPLACEMENT_HEIGHT_SCALE_SUFFIX = "_displacement_blend_height_scale_tx"
DISPLACEMENT_BRANCH_SUFFIX = "_displacement_branch_tx"
FRACTAL_BLEND_SUFFIX = "_fractal_blend_tx"
FRACTAL_BLEND_CLAMP_SUFFIX = "_fractal_blend_clamp_tx"
FRACTAL_BLEND_REMAP_SUFFIX = "_fractal_blend_remap_tx"
SLOPE_BLEND_SUFFIX = "_slope_blend_tx"
SCOPE_BLEND_SUFFIX = "_scope_blend_tx"
SCOPE_OBJ_BLEND_SUFFIX = "_scope"
AO_BLEND_SUFFIX = "_ao_blend_tx"
AO_BLEND_REMAP_SUFFIX = "_ao_blend_remap_tx"
TRIPLANAR_BLEND_SUFFIX = "_triplanar_blend_tx"
WORLD_POSITION_SUFFIX = "_world_pos_tx"
WORLD_POSITION_REORDER_SUFFIX = "_wp_reorder_tx"
HEIGHT_GRADIENT_SUFFIX = "_height_gradient_tx"
DISPLACEMENT_BLEND_SUFFIX = "_displacement_blend_tx"
MULTI_BLEND_SUFFIX = "_multi_blend_tx"
MOISTURE_SUFFIX = "_moisture"

try:
    from user_settings import *

    logging.debug("CUSTOM SETTINGS FOUND")
except ImportError:
    logging.debug("NO CUSTOM SETTINGS FOUND")
