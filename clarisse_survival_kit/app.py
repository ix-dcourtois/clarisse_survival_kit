import json
import logging
from clarisse_survival_kit.selectors import *
from clarisse_survival_kit.utility import *
# Global variable
from clarisse_survival_kit.utility import get_textures_from_directory, get_mtl_from_context, get_disp_from_context, \
    get_attrs_connected_to_texture, check_selection, check_context

PROJECTIONS = ['planar', 'cylindrical', 'spherical', 'cubic', 'camera', 'parametric', 'uv']


class Surface:
    def __init__(self, ix, **kwargs):
        self.ix = ix
        self.ctx = None
        self.name = None
        self.mtl = None
        self.projection = kwargs.get('projection')
        self.uv_scale = kwargs.get('uv_scale')
        self.object_space = kwargs.get('object_space', 0)
        self.ior = kwargs.get('ior', DEFAULT_IOR)
        self.specular_strength = kwargs.get('specular_strength', DEFAULT_SPECULAR_STRENGTH)
        self.height = kwargs.get('height', DEFAULT_DISPLACEMENT_HEIGHT)
        self.triplanar_blend = kwargs.get('triplanar_blend', 0.5)
        self.tile = kwargs.get('tile', True)
        self.textures = {}
        self.streamed_maps = []

    def create_mtl(self, name, target_ctx):
        """Creates a new PhysicalStandard material and context."""
        logging.debug("Creating material...")
        self.name = name
        ctx = self.ix.cmds.CreateContext(name, "Global", str(target_ctx))
        self.ctx = ctx
        mtl = self.ix.cmds.CreateObject(name + MATERIAL_SUFFIX, "MaterialPhysicalStandard", "Global", str(ctx))
        self.ix.cmds.SetValue(str(mtl) + ".specular_1_index_of_refraction", [str(self.ior)])
        self.ix.cmds.SetValue(str(mtl) + ".specular_1_strength", [str(self.specular_strength)])
        self.mtl = mtl
        logging.debug("...done creating material")
        return mtl

    def create_textures(self, textures, color_spaces, streamed_maps=(), clip_opacity=True):
        """Creates all textures from a dict."""
        logging.debug("Creating textures...")
        for index, texture in textures.iteritems():
            kwargs = TEXTURE_SETTINGS.get(index)
            tx = self.create_tx(index, texture, color_spaces[index], **kwargs)
        logging.debug("...done creating textures")

    def update_textures(self, textures, color_spaces, streamed_maps=()):
        logging.debug("Updating textures...")
        for index, texture in textures.iteritems():
            kwargs = TEXTURE_SETTINGS.get(index)
            tx = self.update_tx(index, texture, color_spaces[index], **kwargs)
        logging.debug("...done updating textures")

    def load(self, ctx):
        """Loads and setups the material from an existing context."""
        logging.debug("Loading surface...")
        self.ctx = ctx
        self.name = os.path.basename(str(ctx))
        textures = {}
        # TODO: Recursive search
        objects_array = self.ix.api.OfObjectArray(ctx.get_object_count())
        flags = self.ix.api.CoreBitFieldHelper()
        ctx.get_all_objects(objects_array, flags, False)

        mtl = None
        triplanar = False
        for ctx_member in objects_array:
            logging.debug("Checking ctx member" + str(ctx_member))
            if ctx_member.is_context():
                continue
            if (ctx_member.is_kindof("TextureMapFile") or ctx_member.is_kindof("TextureStreamedMapFile")) \
                    and ctx_member.is_local():
                self.projection = PROJECTIONS[ctx_member.attrs.projection[0]]
                self.object_space = ctx_member.attrs.object_space[0]
                self.uv_scale = [ctx_member.attrs.uv_scale[0], ctx_member.attrs.uv_scale[2]]
            if ctx_member.is_kindof("MaterialPhysicalStandard"):
                if ctx_member.is_local() or not mtl:
                    mtl = ctx_member
                    logging.debug("Material found:" + str(mtl))
            for key, suffix in SUFFIXES.iteritems():
                if ctx_member.get_contextual_name().endswith(suffix):
                    textures[key] = ctx_member
                    logging.debug("Texture found with index:" + str(key))
            if ctx_member.is_kindof("Displacement"):
                self.height = ctx_member.attrs.front_value[0]
                logging.debug("Displacement found:" + str(ctx_member))
            if ctx_member.get_contextual_name().endswith(TRIPLANAR_SUFFIX):
                triplanar = True
                logging.debug("Triplanar tx found:" + str(ctx_member))
                for key, suffix in SUFFIXES.iteritems():
                    if ctx_member.get_contextual_name().endswith(suffix + TRIPLANAR_SUFFIX):
                        textures[key + '_triplanar'] = ctx_member
            if ctx_member.get_contextual_name().endswith(SINGLE_CHANNEL_SUFFIX):
                for key, suffix in SUFFIXES.iteritems():
                    if ctx_member.get_contextual_name().endswith(suffix + SINGLE_CHANNEL_SUFFIX):
                        textures[key + '_reorder'] = ctx_member
                        self.streamed_maps.append(key)
                        logging.debug("Reorder node for stream maps found:" + str(ctx_member))
        if not mtl or not textures:
            self.ix.log_warning("No valid material found.")
            logging.debug("No textures found")
            return None
        if triplanar:
            self.projection = 'triplanar'
        self.textures = textures
        logging.debug("Textures found:" + str(textures))
        self.mtl = mtl
        return mtl

    def update_projection(self, projection="triplanar", uv_scale=DEFAULT_UV_SCALE,
                          triplanar_blend=0.5, object_space=0, tile=True):
        """Updates the projections in each TextureMapFile."""
        print "PROJECTION SET TO: " + projection
        logging.debug("Projection set to:" + projection)
        for key, tx in self.textures.iteritems():
            if (tx.is_kindof("TextureMapFile") or tx.is_kindof("TextureStreamedMapFile")) and tx.is_local():
                if key == "preview":
                    continue
                if projection == "uv":
                    self.ix.cmds.SetValue(str(tx) + ".projection", [str(PROJECTIONS.index('uv'))])
                else:
                    attrs = self.ix.api.CoreStringArray(6)
                    attrs[0] = str(tx) + ".projection"
                    attrs[1] = str(tx) + ".axis"
                    attrs[2] = str(tx) + ".object_space"
                    attrs[3] = str(tx) + ".uv_scale[0]"
                    attrs[4] = str(tx) + ".uv_scale[1]"
                    attrs[5] = str(tx) + ".uv_scale[2]"
                    values = self.ix.api.CoreStringArray(6)
                    values[0] = str(
                        PROJECTIONS.index('cubic') if projection == "triplanar" else PROJECTIONS.index(projection))
                    values[1] = str(1)
                    values[2] = str(object_space)
                    values[3] = str(uv_scale[0])
                    values[4] = str((uv_scale[0] + uv_scale[1]) / 2)
                    values[5] = str(uv_scale[1])
                    self.ix.cmds.SetValues(attrs, values)
                if not tile:
                    attrs = self.ix.api.CoreStringArray(2)
                    attrs[0] = str(tx) + ".u_repeat_mode"
                    attrs[1] = str(tx) + ".v_repeat_mode"
                    values = self.ix.api.CoreStringArray(2)
                    values[0] = str(2)
                    values[1] = str(2)
                    self.ix.cmds.SetValues(attrs, values)
            if (tx.is_kindof("TextureMapFile") or tx.is_kindof("TextureStreamedMapFile")) and \
                            self.projection != "triplanar" and projection == "triplanar":
                tx_to_triplanar(tx, blend=triplanar_blend, object_space=object_space, ix=self.ix)
            if tx.is_kindof("TextureTriplanar") and projection != "triplanar":
                input_tx = self.ix.get_item(str(tx) + ".right").get_texture()
                connected_attrs = self.ix.api.OfAttrVector()
                get_attrs_connected_to_texture(tx, connected_attrs, ix=self.ix)
                for i_attr in range(0, connected_attrs.get_count()):
                    self.ix.cmds.SetTexture([str(connected_attrs[i_attr])], str(input_tx))
                self.ix.cmds.DeleteItems([str(tx)])
        self.projection = projection
        self.object_space = object_space
        self.uv_scale = uv_scale
        self.triplanar_blend = triplanar_blend
        logging.debug("Done changing projections")

    def pre_create_tx(self, index):
        return True

    def create_sub_ctx(self, index):
        sub_ctx = self.ix.item_exists(os.path.join(self.ctx, index))
        if sub_ctx:
            return sub_ctx
        else:
            return self.ix.cmds.CreateContext(index, "Global", str(self.ctx))

    def create_tx(self, index, filename, suffix, color_space, streamed=False, single_channel=False, invert=False,
                  connections=None):
        """Creates a new map or streaming file and if projection is set to triplanar it will be mapped that way."""
        if not self.pre_create_tx(index):
            return None
        triplanar_tx = None
        reorder_tx = None
        logging.debug("create_tx called with arguments:" +
                      "\n".join(
                          [index, filename, suffix, color_space, str(streamed), str(single_channel), str(connections)]))
        target_ctx = self.create_sub_ctx(index)
        if streamed:
            logging.debug("Setting up TextureStreamedMapFile...")
            tx = self.ix.cmds.CreateObject(self.name + suffix, "TextureStreamedMapFile", "Global", str(target_ctx))
            filename = re.sub(r"((?<!\d)\d{4}(?!\d))", "<UDIM>", filename, count=1)
            self.streamed_maps.append(index)
            if single_channel:
                logging.debug("Creating reorder node...")
                reorder_tx = self.ix.cmds.CreateObject(self.name + suffix + SINGLE_CHANNEL_SUFFIX, "TextureReorder",
                                                       "Global", self.ctx)
                self.ix.cmds.SetValue(str(reorder_tx) + ".channel_order[0]", ["rrrr"])
                self.ix.cmds.SetTexture([str(reorder_tx) + ".input"], str(tx))
                self.textures[index + '_reorder'] = reorder_tx
        else:
            logging.debug("Setting up TextureMapFile...")
            tx = self.ix.cmds.CreateObject(self.name + suffix, "TextureMapFile", "Global", str(target_ctx))
            if index == 'preview':
                logging.debug("Done creating preview tx: " + str(tx))
                self.ix.cmds.SetValue(str(tx) + ".filename", [filename])
                self.textures[index] = tx
                return tx
        if self.projection != 'uv':
            attrs = self.ix.api.CoreStringArray(6)
            attrs[0] = str(tx) + ".projection"
            attrs[1] = str(tx) + ".axis"
            attrs[2] = str(tx) + ".object_space"
            attrs[3] = str(tx) + ".uv_scale[0]"
            attrs[4] = str(tx) + ".uv_scale[1]"
            attrs[5] = str(tx) + ".uv_scale[2]"
            values = self.ix.api.CoreStringArray(6)
            values[0] = str(
                PROJECTIONS.index('cubic') if self.projection == "triplanar" else PROJECTIONS.index(self.projection))
            values[1] = str(1)
            values[2] = str(self.object_space)
            values[3] = str(self.uv_scale[0])
            values[4] = str((self.uv_scale[0] + self.uv_scale[1]) / 2)
            values[5] = str(self.uv_scale[1])
            self.ix.cmds.SetValues(attrs, values)
        if self.projection == "triplanar":
            logging.debug("Set up triplanar...")
            triplanar_tx = self.ix.cmds.CreateObject(tx.get_contextual_name() + TRIPLANAR_SUFFIX, "TextureTriplanar",
                                                     "Global", str(target_ctx))
            self.ix.cmds.SetTexture([str(triplanar_tx) + ".right"], str(reorder_tx if reorder_tx else tx))
            self.ix.cmds.SetTexture([str(triplanar_tx) + ".left"], str(reorder_tx if reorder_tx else tx))
            self.ix.cmds.SetTexture([str(triplanar_tx) + ".top"], str(reorder_tx if reorder_tx else tx))
            self.ix.cmds.SetTexture([str(triplanar_tx) + ".bottom"], str(reorder_tx if reorder_tx else tx))
            self.ix.cmds.SetTexture([str(triplanar_tx) + ".front"], str(reorder_tx if reorder_tx else tx))
            self.ix.cmds.SetTexture([str(triplanar_tx) + ".back"], str(reorder_tx if reorder_tx else tx))
            self.ix.cmds.SetValue(str(triplanar_tx) + ".blend", [str(self.triplanar_blend)])
            self.ix.cmds.SetValue(str(triplanar_tx) + ".object_space", [str(self.object_space)])
            self.textures[index + '_triplanar'] = triplanar_tx
        attrs = self.ix.api.CoreStringArray(5 if streamed else 6)
        attrs[0] = str(tx) + ".color_space_auto_detect"
        attrs[1] = str(tx) + ".filename"
        attrs[2] = str(tx) + ".invert"
        attrs[3] = str(tx) + ".u_repeat_mode"
        attrs[4] = str(tx) + ".v_repeat_mode"
        values = self.ix.api.CoreStringArray(5 if streamed else 6)
        values[0] = '0'
        values[1] = str(filename)
        values[2] = str(1 if invert else 0)
        values[3] = str((2 if not self.tile else 0))
        values[4] = str((2 if not self.tile else 0))
        if not streamed:
            attrs[5] = str(tx) + ".single_channel_file_behavior"
            values[5] = str((1 if single_channel else 0))
        self.ix.cmds.SetValues(attrs, values)
        self.ix.application.check_for_events()
        self.ix.cmds.SetValue(str(tx) + ".file_color_space", [str(color_space)])
        self.textures[index] = tx
        if connections:
            for connection in connections:
                if self.projection == "triplanar":
                    self.ix.cmds.SetTexture([connection], str(triplanar_tx))
                else:
                    self.ix.cmds.SetTexture([connection], str(reorder_tx if reorder_tx else tx))
        self.post_create_tx(index, tx)
        logging.debug("Done creating tx: " + str(tx))
        return tx

    def post_create_tx(self, index, tx):
        """Creates certain files at the end of the create_tx function call."""
        logging.debug("Post create function called for: " + index)
        post_tx = None
        if index == "ao":
            post_tx = self.create_ao_blend()
        elif index == "displacement":
            post_tx = self.create_displacement_map()
        elif index == "normal":
            post_tx = self.create_normal_map()
        elif index == "bump":
            post_tx = self.create_bump_map()
        elif index == "ior":
            post_tx = self.create_ior_divide_tx()
        logging.debug("Post texture: " + str(post_tx))
        return post_tx

    def create_displacement_map(self):
        """Creates a Displacement map if it doesn't exist."""
        logging.debug("Creating displacement map...")
        if not self.get('displacement'):
            self.ix.log_warning("No displacement texture was found.")
            return None
        if self.projection == 'triplanar':
            disp_tx = self.get('displacement_triplanar')
        else:
            if self.get('displacement_reorder'):
                disp_tx = self.get('displacement_reorder')
            else:
                disp_tx = self.get('displacement')
        disp = self.ix.cmds.CreateObject(self.name + DISPLACEMENT_MAP_SUFFIX, "Displacement",
                                         "Global", str(self.ctx))
        attrs = self.ix.api.CoreStringArray(5)
        attrs[0] = str(disp) + ".bound[0]"
        attrs[1] = str(disp) + ".bound[1]"
        attrs[2] = str(disp) + ".bound[2]"
        attrs[3] = str(disp) + ".front_value"
        attrs[4] = str(disp) + ".front_offset"
        values = self.ix.api.CoreStringArray(5)
        values[0] = str(self.height * 1.1)
        values[1] = str(self.height * 1.1)
        values[2] = str(self.height * 1.1)
        values[3] = str(self.height)
        values[4] = str((self.height / 2) * -1)
        self.ix.cmds.SetValues(attrs, values)
        self.ix.cmds.SetTexture([str(disp) + ".front_value"], str(disp_tx))
        self.textures['displacement_map'] = disp
        return disp

    def create_normal_map(self):
        """Creates a Normal map if it doesn't exist."""
        logging.debug("Creating normal map...")
        if not self.get('normal'):
            self.ix.log_warning("No normal texture was found.")
            return None
        if self.projection == 'triplanar':
            normal_tx = self.get('normal_triplanar')
        else:
            normal_tx = self.get('normal')
        normal_map = self.ix.cmds.CreateObject(self.name + NORMAL_MAP_SUFFIX, "TextureNormalMap",
                                               "Global", str(self.ctx))
        self.ix.cmds.SetTexture([str(normal_map) + ".input"], str(normal_tx))
        self.ix.cmds.SetTexture([str(self.mtl) + ".normal_input"], str(normal_map))
        self.textures['normal_map'] = normal_map
        return normal_map

    def create_ao_blend(self):
        """Creates a AO blend texture if it doesn't exist."""
        logging.debug("Creating ao blend texture...")
        if not self.get('ao'):
            self.ix.log_warning("No ao texture was found.")
            return None
        if self.projection == 'triplanar':
            ao_tx = self.get('ao_triplanar')
        else:
            if self.get('ao_reorder'):
                ao_tx = self.get('ao_reorder')
            else:
                ao_tx = self.get('ao')

        ao_blend_tx = self.ix.cmds.CreateObject(self.name + AO_BLEND_SUFFIX, "TextureBlend", "Global", str(self.ctx))
        self.ix.cmds.SetTexture([str(ao_blend_tx) + ".input1"], str(self.get('diffuse')))
        self.ix.cmds.SetTexture([str(ao_blend_tx) + ".input2"], str(ao_tx))
        self.ix.cmds.SetValue(str(ao_blend_tx) + ".mode", [str(7)])
        self.ix.cmds.SetValue(str(ao_blend_tx) + ".mix", [str(DEFAULT_AO_BLEND_STRENGTH)])
        self.textures["ao_blend"] = ao_blend_tx
        self.ix.cmds.SetTexture([str(self.mtl) + ".diffuse_front_color"], str(ao_blend_tx))
        return ao_blend_tx

    def create_bump_map(self):
        """Creates a Bump map if it doesn't exist."""
        logging.debug("Creating bump map...")
        if not self.get('bump'):
            self.ix.log_warning("No bump texture was found.")
            return None
        if self.projection == 'triplanar':
            bump_tx = self.get('bump_triplanar')
        else:
            if self.get('bump_reorder'):
                bump_tx = self.get('bump_reorder')
            else:
                bump_tx = self.get('bump')
        bump_map = self.ix.cmds.CreateObject(self.name + BUMP_MAP_SUFFIX, "TextureBumpMap",
                                             "Global", str(self.ctx))
        self.ix.cmds.SetTexture([str(bump_map) + ".input"], str(bump_tx))
        self.ix.cmds.SetTexture([str(self.mtl) + ".normal_input"], str(bump_map))
        self.textures['bump_map'] = bump_map
        return bump_map

    def create_ior_divide_tx(self):
        """Creates an IOR divide helper texture if it doesn't exist."""
        logging.debug("Creating IOR divide texture...")
        if not self.get('ior'):
            self.ix.log_warning("No ior texture was found.")
            return None
        if self.projection == 'triplanar':
            ior_tx = self.get('ior_triplanar')
        else:
            if self.get('ior_reorder'):
                ior_tx = self.get('ior_reorder')
            else:
                ior_tx = self.get('ior')

        logging.debug("Using following texture as input2 for divide: " + str(ior_tx))
        ior_divide_tx = self.ix.cmds.CreateObject(self.name + IOR_DIVIDE_SUFFIX, "TextureDivide",
                                                  "Global", str(self.ctx))
        ior_divide_tx.attrs.input1[0] = 1.0
        ior_divide_tx.attrs.input1[1] = 1.0
        ior_divide_tx.attrs.input1[2] = 1.0
        self.ix.cmds.SetTexture([str(ior_divide_tx) + ".input2"], str(ior_tx))
        self.ix.application.check_for_events()
        self.textures['ior_divide'] = ior_divide_tx
        if self.mtl.get_attribute('specular_1_index_of_refraction').is_editable():
            self.ix.cmds.SetTexture([str(self.mtl) + ".specular_1_index_of_refraction"], str(ior_divide_tx))
            self.ix.application.check_for_events()
            self.ior = ior_tx
        else:
            logging.debug("IOR was locked")
        return ior_divide_tx

    def update_ior(self, ior):
        """Updates the IOR.
        Make sure floats have 1 precision. 1.6 will work, but 1.65 will crash Clarisse.
        """
        logging.debug("Updating IOR...")
        if self.mtl.get_attribute('specular_1_index_of_refraction').is_editable():
            self.ix.cmds.SetTexture([str(self.mtl) + ".specular_1_index_of_refraction"], str(ior))
            self.ix.application.check_for_events()
            self.ior = ior
        else:
            logging.debug("IOR was locked")

    def update_tx(self, index, filename, suffix, color_space, streamed=False, single_channel=False, invert=False):
        """Updates a texture by changing the filename or color space settings."""
        logging.debug("update_tx called with arguments:" +
                      "\n".join([index, filename, suffix, color_space, str(streamed), str(single_channel)]))
        tx = self.get(index)
        if tx.is_kindof("TextureStreamedMapFile") != streamed:
            logging.debug("Map is no longer Map file or Stream Map. Switch in progress...")
            self.destroy_tx(index)
            self.create_textures({index: filename}, {index: color_space}, [index] if streamed else [])
            logging.debug("Texture recreated as: " + str(self.get(index)))
            tx = self.get(index)
        attrs = self.ix.api.CoreStringArray(3 if streamed else 4)
        attrs[0] = str(tx) + ".file_color_space"
        attrs[1] = str(tx) + ".filename"
        attrs[2] = str(tx) + ".invert"
        values = self.ix.api.CoreStringArray(3 if streamed else 4)
        values[0] = color_space
        values[1] = filename
        values[2] = str((1 if invert else 0))
        if not streamed:
            attrs[3] = str(tx) + ".single_channel_file_behavior"
            values[3] = str((1 if single_channel else 0))
        self.ix.cmds.SetValues(attrs, values)
        # self.ix.cmds.RenameItem(str(tx), self.name + suffix)
        # self.ix.application.check_for_events()
        return tx

    def update_displacement(self, height):
        """Updates a Displacement map with new height settings."""
        logging.debug("Updating displacement...")
        disp = self.get('displacement_map')
        if disp:
            attrs = self.ix.api.CoreStringArray(5)
            attrs[0] = str(disp) + ".bound[0]"
            attrs[1] = str(disp) + ".bound[1]"
            attrs[2] = str(disp) + ".bound[2]"
            attrs[3] = str(disp) + ".front_value"
            attrs[4] = str(disp) + ".front_offset"
            values = self.ix.api.CoreStringArray(5)
            values[0] = str(height * 1.1)
            values[1] = str(height * 1.1)
            values[2] = str(height * 1.1)
            values[3] = str(height)
            values[4] = str((height / 2) * -1)
            self.ix.cmds.SetValues(attrs, values)
        self.height = height

    def update_opacity(self, clip_opacity, found_textures, update_textures):
        """Connect/Disconnect the opacity texture depending if clip_opacity is set to False/True."""
        logging.debug("Updating opacity...")
        if 'opacity' in update_textures and 'opacity' in found_textures:
            if clip_opacity and self.ix.get_item(str(self.mtl) + '.opacity').get_texture():
                self.ix.cmds.SetTexture([str(self.mtl) + ".opacity"], '')
            elif not clip_opacity and not self.ix.get_item(str(self.mtl) + '.opacity').get_texture():
                self.ix.cmds.SetTexture([str(self.mtl) + ".opacity"], str(self.get('opacity')))

    def update_names(self, name):
        """Updates all texture names used in the context."""
        logging.debug("Updating names...")
        ctx = self.ctx
        self.ix.cmds.RenameItem(str(ctx), name)

        objects_array = self.ix.api.OfObjectArray(ctx.get_object_count())
        flags = self.ix.api.CoreBitFieldHelper()
        ctx.get_all_objects(objects_array, flags, False)

        for ctx_member in objects_array:
            logging.debug(
                "Updating name from " + str(ctx_member) + " to " + ctx_member.get_contextual_name().replace(self.name,
                                                                                                            name))
            self.ix.cmds.RenameItem(str(ctx_member), ctx_member.get_contextual_name().replace(self.name, name))
        self.name = name

    def destroy_tx(self, index):
        """Removes a texture and its pair."""
        logging.debug("Removing the following index from material: " + index)
        if index == 'displacement':
            self.destroy_tx('displacement_map')
        elif index == 'normal':
            self.destroy_tx('normal_map')
        elif index == 'bump':
            self.destroy_tx('bump_map')
        elif index == 'ior':
            self.destroy_tx('ior_divide')
        elif index == 'ao':
            self.destroy_tx('ao_blend')

        if self.get(index + '_reorder'):
            self.destroy_tx(index + '_reorder')
        # Remove triplanar pair. If texture is triplanar avoid infinite recursion.
        if self.projection == 'triplanar' and not index.endswith('_triplanar'):
            self.destroy_tx(index + "_triplanar")
        self.ix.cmds.DeleteItems([str(self.get(index))])
        self.textures.pop(index, None)
        logging.debug("Done removing: " + index)

    def get(self, index):
        """Returns a texture."""
        return self.textures.get(index)

    def clean(self):
        """Resets the emissive or translucency attributes to 0 when not used."""
        logging.debug("Cleanup...")
        if not self.get('emissive'):
            self.ix.cmds.SetValue(str(self.mtl) + ".emission_strength", [str(0)])
        if not self.get('translucency'):
            self.ix.cmds.SetValue(str(self.mtl) + ".diffuse_back_strength", [str(0)])


def get_json_data_from_directory(directory):
    """Get the JSON data contents required for material setup."""
    logging.debug("Searching for JSON...")
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    # Search for any JSON file. Custom Mixer scans don't have a suffix like the ones from the library.
    data = {}
    for f in files:
        filename, extension = os.path.splitext(f)
        if extension == ".json":
            logging.debug("...JSON found!!!")
            with open(os.path.join(directory, filename + ".json")) as json_file:
                json_data = json.load(json_file)
                if not json_data:
                    return None
                meta_data = json_data.get('meta')
                if not meta_data:
                    return None
                categories = json_data.get('categories')
                if not categories:
                    return None
                logging.debug("JSON follows Megascans structure.")
                if categories:
                    if "3d" in categories:
                        data['type'] = '3d'
                    if "atlas" in categories:
                        data['type'] = 'atlas'
                    if "3dplant" in categories:
                        data['type'] = '3dplant'
                if meta_data:
                    for md in meta_data:
                        if md['key'] == "height":
                            data['surface_height'] = float((md['value']).replace("m", "").replace(" ", ""))
                        elif md['key'] == "scanArea":
                            data['scan_area'] = [float(val) for val in
                                                 (md['value']).replace("m", "").replace(" ", "").split("x")]
                        elif md['key'] == "tileable":
                            data['tileable'] = md['value']
    return data


def import_asset(asset_directory, target_ctx=None, ior=DEFAULT_IOR, projection_type="triplanar", object_space=0,
                 clip_opacity=True, srgb=None, triplanar_blend=0.5, **kwargs):
    """Imports a surface, atlas or object."""
    logging.debug("Importing asset...")
    ix = get_ix(kwargs.get("ix"))
    if not target_ctx:
        target_ctx = ix.application.get_working_context()
    if not check_context(target_ctx, ix=ix):
        return None
    asset_directory = os.path.normpath(asset_directory)
    if not os.path.isdir(asset_directory):
        return ix.log_warning("Invalid directory specified: " + asset_directory)
    logging.debug("Asset directory: " + asset_directory)

    # Initial data
    json_data = get_json_data_from_directory(asset_directory)
    logging.debug("JSON data:")
    logging.debug(str(json_data))
    if not json_data:
        ix.log_warning("Could not find a Megascans JSON file. Defaulting to standard settings.")
    asset_type = json_data.get('type', "surface")
    logging.debug("Asset type from JSON test: " + asset_type)
    surface_height = json_data.get('surface_height', DEFAULT_DISPLACEMENT_HEIGHT)
    logging.debug("Surface height JSON test: " + str(surface_height))
    scan_area = json_data.get('scan_area', DEFAULT_UV_SCALE)
    logging.debug("Scan area JSON test: " + str(scan_area))
    tileable = json_data.get('tileable', True)
    asset_name = os.path.basename(os.path.normpath(asset_directory))
    logging.debug("Asset name: " + asset_name)

    if asset_type in ["3d", "atlas", "3dplant"]:
        projection_type = 'uv'
    logging.debug("Initial projection type: " + projection_type)

    if asset_type == '3dplant':
        # Megascans 3dplant importer. The 3dplant importer requires 2 materials to be created.
        # Let's first find the textures of the Atlas and create the material.
        atlas_textures = get_textures_from_directory(os.path.join(asset_directory, 'Textures/Atlas/'))
        if not atlas_textures:
            ix.log_warning("No textures found in directory.")
            return None
        logging.debug("Atlas textures: ")
        logging.debug(str(atlas_textures))
        streamed_maps = get_stream_map_files(atlas_textures)
        logging.debug("Atlas streamed maps: ")
        logging.debug(str(streamed_maps))

        atlas_surface = Surface(ix, projection='uv', uv_scale=scan_area, height=DEFAULT_PLANT_DISPLACEMENT_HEIGHT,
                                tile=tileable, object_space=object_space, triplanar_blend=triplanar_blend, ior=ior)
        plant_root_ctx = ix.cmds.CreateContext(asset_name, "Global", str(target_ctx))
        atlas_mtl = atlas_surface.create_mtl(ATLAS_CTX, plant_root_ctx)
        atlas_surface.create_textures(atlas_textures, srgb, streamed_maps=streamed_maps, clip_opacity=clip_opacity)
        atlas_ctx = atlas_surface.ctx
        # Find the textures of the Billboard and create the material.
        billboard_textures = get_textures_from_directory(os.path.join(asset_directory, 'Textures/Billboard/'))
        if not billboard_textures:
            ix.log_warning("No textures found in directory.")
            return None
        logging.debug("Billboard textures: ")
        logging.debug(str(billboard_textures))

        streamed_maps = get_stream_map_files(billboard_textures)
        logging.debug("Billboard streamed maps: ")
        logging.debug(str(streamed_maps))
        billboard_surface = Surface(ix, projection='uv', uv_scale=scan_area, height=surface_height,
                                    tile=tileable, object_space=object_space, triplanar_blend=triplanar_blend, ior=ior)
        billboard_mtl = billboard_surface.create_mtl(BILLBOARD_CTX, plant_root_ctx)
        billboard_surface.create_textures(billboard_textures, srgb, streamed_maps=streamed_maps,
                                          clip_opacity=clip_opacity)
        billboard_ctx = billboard_surface.ctx

        for dir_name in os.listdir(asset_directory):
            variation_dir = os.path.join(asset_directory, dir_name)
            if os.path.isdir(variation_dir) and dir_name.startswith('Var'):
                logging.debug("Variation dir found: " + variation_dir)
                files = [f for f in os.listdir(variation_dir) if os.path.isfile(os.path.join(variation_dir, f))]
                # Search for models files and apply material
                objs = []
                for f in files:
                    filename, extension = os.path.splitext(f)
                    if extension == ".obj":
                        logging.debug("Found obj: " + f)
                        filename, extension = os.path.splitext(f)
                        polyfile = ix.cmds.CreateObject(filename, "GeometryPolyfile", "Global", str(plant_root_ctx))
                        ix.cmds.SetValue(str(polyfile) + ".filename",
                                         [os.path.normpath(os.path.join(variation_dir, f))])
                        # Megascans .obj files are saved in cm, Clarisse imports them as meters.
                        polyfile.attrs.scale_offset[0] = .01
                        polyfile.attrs.scale_offset[1] = .01
                        polyfile.attrs.scale_offset[2] = .01
                        geo = polyfile.get_module()
                        for i in range(geo.get_shading_group_count()):
                            if filename.endswith('3'):
                                geo.assign_material(billboard_mtl.get_module(), i)
                                if clip_opacity and billboard_surface.get('opacity'):
                                    geo.assign_clip_map((billboard_surface.get('opacity')).get_module(), i)
                            else:
                                geo.assign_material(atlas_mtl.get_module(), i)
                                if clip_opacity and atlas_surface.get('opacity'):
                                    geo.assign_clip_map(atlas_surface.get('opacity').get_module(), i)
                                lod_level_match = re.sub('.*?([0-9]*)$', r'\1', filename)
                                if int(lod_level_match) in ATLAS_LOD_DISPLACEMENT_LEVELS:
                                    geo.assign_displacement(atlas_surface.get('displacement_map').get_module(), i)
                    elif extension == ".abc":
                        logging.debug("Found abc: " + f)
                        abc_reference = ix.cmds.CreateFileReference(str(plant_root_ctx),
                                                                    [os.path.normpath(os.path.join(variation_dir, f))])

        shading_layer = ix.cmds.CreateObject(asset_name + SHADING_LAYER_SUFFIX, "ShadingLayer", "Global",
                                             str(plant_root_ctx))
        logging.debug("Creating shading layers")
        for i in range(0, 4):
            ix.cmds.AddShadingLayerRule(str(shading_layer), i, ["filter", "", "is_visible", "1"])
            ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "filter", ["./*LOD" + str(i) + "*"])
            ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "material", [str(atlas_mtl)])
            if atlas_surface.get('opacity') and clip_opacity:
                ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "clip_map",
                                                     [str(atlas_surface.get('opacity'))])
            if atlas_surface.get('displacement') and i in ATLAS_LOD_DISPLACEMENT_LEVELS:
                ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "displacement",
                                                     [str(atlas_surface.get('displacement_map'))])

            group = ix.cmds.CreateObject(asset_name + "_LOD" + str(i) + GROUP_SUFFIX, "Group", "Global",
                                         str(plant_root_ctx))
            group.attrs.inclusion_rule = "./*LOD" + str(i) + "*"
            ix.cmds.AddValues([group.get_full_name() + ".filter"], ["GeometryAbcMesh"])
            ix.cmds.AddValues([group.get_full_name() + ".filter"], ["GeometryPolyfile"])
            ix.cmds.RemoveValue([group.get_full_name() + ".filter"], [2, 0, 1])

    else:
        # All assets except 3dplant have the material in the root directory of the asset.
        logging.debug("Searching for textures: ")
        textures = get_textures_from_directory(asset_directory)
        if not textures:
            return ix.log_warning("No textures found in directory.")
        logging.debug("Found textures: ")
        logging.debug(str(textures))
        streamed_maps = get_stream_map_files(textures)
        if streamed_maps:
            logging.debug("Streamed maps: ")
            logging.debug(str(streamed_maps))

        surface = Surface(ix, projection=projection_type, uv_scale=scan_area, height=surface_height, tile=tileable,
                          object_space=object_space, triplanar_blend=triplanar_blend, ior=ior)
        mtl = surface.create_mtl(asset_name, target_ctx)
        surface.create_textures(textures, srgb, streamed_maps, clip_opacity=clip_opacity)
        ctx = surface.ctx

        if asset_type == '3d':
            # Megascans geometry handling. OBJ files will have materials assigned to them.
            lod_mtls = {}
            if 'normal_lods' in textures and 'normal' in textures:
                logging.debug("Setting up normal lods: ")
                normal_lods = {}
                for normal_lod_file in textures['normal_lods']:
                    logging.debug(str(normal_lod_file))
                    lod_filename, lod_ext = os.path.splitext(normal_lod_file)
                    lod_level_match = re.sub('.*?([0-9]*)$', r'\1', lod_filename)
                    lod_level = int(lod_level_match)
                    logging.debug("LOD level: " + str(lod_level))
                    lod_mtl = ix.cmds.Instantiate([str(mtl)])[0]
                    ix.cmds.LocalizeAttributes([str(lod_mtl) + ".normal_input"], True)
                    ix.cmds.RenameItem(str(lod_mtl), asset_name + MATERIAL_LOD_SUFFIX % lod_level)
                    normal_lod_tx = ix.cmds.Instantiate([str(surface.get('normal'))])[0]
                    ix.cmds.LocalizeAttributes([str(normal_lod_tx) + ".filename"], True)
                    ix.cmds.RenameItem(str(normal_lod_tx), asset_name + NORMAL_LOD_SUFFIX % lod_level)
                    normal_lod_map = ix.cmds.CreateObject(asset_name + NORMAL_MAP_LOD_SUFFIX % lod_level,
                                                          "TextureNormalMap", "Global", str(ctx))
                    ix.cmds.SetTexture([str(lod_mtl) + ".normal_input"], str(normal_lod_map))
                    ix.cmds.SetTexture([str(normal_lod_map) + ".input"], str(normal_lod_tx))
                    ix.cmds.SetValue(str(normal_lod_tx) + ".filename", [normal_lod_file])
                    normal_lods[lod_level] = normal_lod_tx
                    lod_mtls[lod_level_match] = lod_mtl
                    lod_level += 1
            files = [f for f in os.listdir(asset_directory) if os.path.isfile(os.path.join(asset_directory, f))]
            instance_geo = None
            for f in files:
                filename, extension = os.path.splitext(f)
                if extension == ".obj":
                    logging.debug("Found normal lod obj: " + f)
                    if "normal_lods" in textures and re.search(r'_LOD[0-9]$', filename, re.IGNORECASE):
                        lod_level = re.sub('.*?([0-9]*)$', r'\1', filename)
                        # print "Found LOD = " + str(lod_level)
                        object_material = lod_mtls[lod_level]
                    else:
                        object_material = mtl
                    # TODO: Instancing doesn't work properly. RenameItem runs asynchronously after assignment causing issues.
                    # if instance_geo:
                    #     polyfile = ix.cmds.Instantiate([str(instance_geo)])[0]
                    #     ix.cmds.LocalizeAttributes([str(polyfile) + ".filename"], True)
                    #     ix.cmds.RenameItem(str(polyfile), filename)
                    # else:
                    # instance_geo = polyfile
                    polyfile = ix.cmds.CreateObject(filename, "GeometryPolyfile", "Global", str(ctx))
                    ix.cmds.SetValue(str(polyfile) + ".filename", [os.path.normpath(os.path.join(asset_directory, f))])
                    # Megascans .obj files are saved in cm, Clarisse imports them as meters.
                    polyfile.attrs.scale_offset[0] = .01
                    polyfile.attrs.scale_offset[1] = .01
                    polyfile.attrs.scale_offset[2] = .01
                    geo = polyfile.get_module()
                    for i in range(geo.get_shading_group_count()):
                        geo.assign_material(object_material.get_module(), i)
                        if clip_opacity and textures.get('opacity'):
                            geo.assign_clip_map(surface.get('opacity').get_module(), i)
                        if not filename.endswith("_High") and textures.get('displacement'):
                            geo.assign_displacement(surface.get('displacement_map').get_module(), i)
                elif extension == ".abc":
                    abc_reference = ix.cmds.CreateFileReference(str(ctx),
                                                                [os.path.normpath(os.path.join(asset_directory, f))])
            logging.debug("Creating shading layers..")
            shading_layer = ix.cmds.CreateObject(asset_name + SHADING_LAYER_SUFFIX, "ShadingLayer", "Global",
                                                 str(ctx))
            ix.cmds.AddShadingLayerRule(str(shading_layer), 0, ["filter", "", "is_visible", "1"])
            ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "filter", ["./*_High"])
            ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "material", [str(mtl)])
            if surface.get('opacity') and clip_opacity:
                ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "clip_map",
                                                     [str(surface.get('opacity'))])
            if lod_mtls:
                i = 0
                for lod_level, lod_mtl in lod_mtls.iteritems():
                    ix.cmds.AddShadingLayerRule(str(shading_layer), i, ["filter", "", "is_visible", "1"])
                    ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "filter", ["./*LOD" + str(lod_level)])
                    ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "material", [str(lod_mtl)])
                    if surface.get('opacity') and clip_opacity:
                        ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "clip_map",
                                                             [str(surface.get('opacity'))])
                    if surface.get('displacement'):
                        if i in MESH_LOD_DISPLACEMENT_LEVELS:
                            ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [i], "displacement",
                                                                 [str(surface.get('displacement_map'))])
                    i += 1
            logging.debug("...done creating shading layers")
        elif asset_type == "atlas":
            logging.debug("Setting up atlas...")
            files = [f for f in os.listdir(asset_directory) if os.path.isfile(os.path.join(asset_directory, f))]
            polyfiles = []
            for key, f in enumerate(files):
                filename, extension = os.path.splitext(f)
                if extension == ".obj":
                    logging.debug("Found obj: " + f)
                    polyfile = ix.cmds.CreateObject(filename, "GeometryPolyfile", "Global",
                                                    str(ctx))
                    polyfile.attrs.filename = os.path.normpath(os.path.join(asset_directory, f))
                    geo = polyfile.get_module()
                    for i in range(geo.get_shading_group_count()):
                        geo.assign_material(mtl.get_module(), i)
                        if textures.get('opacity') and clip_opacity:
                            geo.assign_clip_map(surface.get('opacity').get_module(), i)
                    polyfiles.append(polyfile)
                elif extension == ".abc":
                    logging.debug("Found abc: " + f)
                    abc_reference = ix.cmds.CreateFileReference(str(ctx),
                                                                [os.path.normpath(os.path.join(asset_directory, f))])
            logging.debug("Setting up shading layer: ")
            if files:
                shading_layer = ix.cmds.CreateObject("shading_layer", "ShadingLayer", "Global",
                                                     str(ctx))
                ix.cmds.AddShadingLayerRule(str(shading_layer), 0, ["filter", "", "is_visible", "1"])
                ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "filter", ["./*"])
                ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "material", [str(mtl)])
                if textures.get('opacity'):
                    ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "clip_map",
                                                         [str(surface.get('opacity'))])
                if textures.get('displacement'):
                    ix.cmds.SetShadingLayerRulesProperty(str(shading_layer), [0], "displacement",
                                                         [str(surface.get('displacement_map'))])
            group = ix.cmds.CreateObject("geometry_group", "Group", "Global", str(ctx))
            group.attrs.inclusion_rule = "./*"
            ix.cmds.AddValues([group.get_full_name() + ".filter"], ["GeometryAbcMesh"])
            ix.cmds.AddValues([group.get_full_name() + ".filter"], ["GeometryPolyfile"])
            ix.cmds.RemoveValue([group.get_full_name() + ".filter"], [2, 0, 1])
            logging.debug("...done setting up shading layer and atlas")
        logging.debug("Finished importing asset.")
        logging.debug("+++++++++++++++++++++++++++++++")
        return surface


def moisten_surface(ctx,
                    height_blend=True,
                    fractal_blend=False,
                    displacement_blend=False,
                    scope_blend=False,
                    slope_blend=False,
                    triplanar_blend=False,
                    ao_blend=False,
                    ior=MOISTURE_DEFAULT_IOR,
                    diffuse_multiplier=MOISTURE_DEFAULT_DIFFUSE_MULTIPLIER,
                    specular_multiplier=MOISTURE_DEFAULT_SPECULAR_MULTIPLIER,
                    roughness_multiplier=MOISTURE_DEFAULT_ROUGHNESS_MULTIPLIER,
                    **kwargs):
    """Moistens the selected material."""
    logging.debug("Moistening context: " + str(ctx))
    ix = get_ix(kwargs.get("ix"))
    if not check_context(ctx, ix=ix):
        return None
    objects_array = ix.api.OfObjectArray(ctx.get_object_count())
    flags = ix.api.CoreBitFieldHelper()
    ctx.get_all_objects(objects_array, flags, False)
    surface_name = os.path.basename(str(ctx))

    mtl = None
    diffuse_tx = None
    specular_tx = None
    roughness_tx = None
    disp = None
    disp_tx = None
    for ctx_member in objects_array:
        if ctx_member.get_contextual_name().endswith(DIFFUSE_SUFFIX):
            diffuse_tx = ctx_member
        if ctx_member.get_contextual_name().endswith(SPECULAR_COLOR_SUFFIX):
            specular_tx = ctx_member
        if ctx_member.get_contextual_name().endswith(SPECULAR_ROUGHNESS_SUFFIX):
            roughness_tx = ctx_member
        if ctx_member.is_kindof("MaterialPhysicalStandard"):
            if ctx_member.is_local() or not mtl:
                mtl = ctx_member
        if ctx_member.is_kindof("Displacement"):
            disp = ctx_member
        if ctx_member.get_contextual_name().endswith(DISPLACEMENT_SUFFIX):
            disp_tx = ctx_member
    if not mtl:
        logging.debug("No MaterialPhysicalStandard found in ctx")
        ix.log_warning("No MaterialPhysicalStandard found in context.")
        return False
    if not disp and not disp_tx and displacement_blend:
        logging.debug("No displacement found in ctx")
        ix.log_warning("No Displacement found in context. Cannot use Displacement blending.")
        return False
    elif not diffuse_tx or not specular_tx or not roughness_tx:
        logging.debug("No diffuse, specular or roughness found")
        ix.log_warning("Make sure the material has a diffuse, specular and roughness texture.")
        return False
    logging.debug("Creating selectors...")
    multi_blend_tx = ix.cmds.CreateObject(surface_name + MOISTURE_SUFFIX + MULTI_BLEND_SUFFIX, "TextureMultiBlend",
                                          "Global", str(ctx))
    # Setup fractal noise
    fractal_selector = create_fractal_selector(ctx, surface_name, MOISTURE_SUFFIX, ix=ix)

    # Setup slope gradient
    slope_selector = create_slope_selector(ctx, surface_name, MOISTURE_SUFFIX, ix=ix)

    # Setup scope
    scope_selector = create_scope_selector(ctx, surface_name, MOISTURE_SUFFIX, ix=ix)

    # Setup triplanar
    triplanar_selector = create_triplanar_selector(ctx, surface_name, MOISTURE_SUFFIX, ix=ix)

    # Setup AO
    ao_selector = create_ao_selector(ctx, surface_name, MOISTURE_SUFFIX, ix=ix)

    # Setup height blend
    height_selector = create_height_selector(ctx, surface_name, MOISTURE_SUFFIX, ix=ix, invert=True)

    disp_selector = None
    # Setup displacement blend
    if disp and disp_tx:
        disp_selector = create_displacement_selector(disp_tx, ctx, surface_name, "_moisture", ix=ix)

    logging.debug("Assigning selectors")
    multi_blend_tx.attrs.layer_1_label[0] = "Base intensity"
    # Attach Ambient Occlusion blend
    multi_blend_tx.attrs.enable_layer_2 = True
    multi_blend_tx.attrs.layer_2_mode = 1
    multi_blend_tx.attrs.layer_2_label[0] = "Ambient Occlusion Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_2_color"], str(ao_selector))
    if not ao_blend: multi_blend_tx.attrs.enable_layer_2 = False
    # Attach displacement blend
    if disp_selector:
        multi_blend_tx.attrs.enable_layer_3 = True
        multi_blend_tx.attrs.layer_3_label[0] = "Displacement Blend"
        multi_blend_tx.attrs.layer_3_mode = 1
        ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_3_color"], str(disp_selector))
        if not displacement_blend: multi_blend_tx.attrs.enable_layer_3 = False
    # Attach height blend
    multi_blend_tx.attrs.enable_layer_4 = True
    multi_blend_tx.attrs.layer_4_mode = 1
    multi_blend_tx.attrs.layer_4_label[0] = "Height Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_4_color"], str(height_selector))
    if not height_blend: multi_blend_tx.attrs.enable_layer_4 = False
    # Attach slope blend
    multi_blend_tx.attrs.enable_layer_5 = True
    multi_blend_tx.attrs.layer_5_mode = 1
    multi_blend_tx.attrs.layer_5_label[0] = "Slope Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_5_color"], str(slope_selector))
    if not slope_blend: multi_blend_tx.attrs.enable_layer_5 = False
    # Attach triplanar blend
    multi_blend_tx.attrs.enable_layer_6 = True
    multi_blend_tx.attrs.layer_6_mode = 1
    multi_blend_tx.attrs.layer_6_label[0] = "Triplanar Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_6_color"], str(triplanar_selector))
    if not triplanar_blend: multi_blend_tx.attrs.enable_layer_6 = False
    # Attach scope blend
    multi_blend_tx.attrs.enable_layer_7 = True
    multi_blend_tx.attrs.layer_7_mode = 1
    multi_blend_tx.attrs.layer_7_label[0] = "Scope Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_7_color"], str(scope_selector))
    if not scope_blend: multi_blend_tx.attrs.enable_layer_7 = False
    # Attach fractal blend
    multi_blend_tx.attrs.enable_layer_8 = True
    multi_blend_tx.attrs.layer_8_label[0] = "Fractal Blend"
    multi_blend_tx.attrs.layer_8_mode = 4 if True in [ao_blend, height_blend, slope_blend, scope_blend] else 1
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_8_color"], str(fractal_selector))
    if not fractal_blend: multi_blend_tx.attrs.enable_layer_8 = False

    # Setup diffuse blend
    logging.debug("Setup diffuse blend")
    diffuse_blend_tx = ix.cmds.CreateObject(surface_name + MOISTURE_DIFFUSE_BLEND_SUFFIX, "TextureBlend", "Global",
                                            str(ctx))
    diffuse_blend_tx.attrs.input1[0] = diffuse_multiplier
    diffuse_blend_tx.attrs.input1[1] = diffuse_multiplier
    diffuse_blend_tx.attrs.input1[2] = diffuse_multiplier
    diffuse_blend_tx.attrs.mode = 7
    ix.cmds.SetTexture([str(diffuse_blend_tx) + ".mix"], str(multi_blend_tx))

    connected_attrs = ix.api.OfAttrVector()
    get_attrs_connected_to_texture(diffuse_tx, connected_attrs, ix=ix)
    for i_attr in range(0, connected_attrs.get_count()):
        logging.debug("Replace attr: " + str(connected_attrs[i_attr]))
        ix.cmds.SetTexture([str(connected_attrs[i_attr])], str(diffuse_blend_tx))
    ix.cmds.SetTexture([str(diffuse_blend_tx) + ".input2"], str(diffuse_tx))

    # Setup specular blend
    logging.debug("Setup specular blend")
    specular_blend_tx = ix.cmds.CreateObject(surface_name + MOISTURE_SPECULAR_BLEND_SUFFIX, "TextureBlend", "Global",
                                             str(ctx))
    ix.cmds.SetTexture([str(specular_blend_tx) + ".mix"], str(multi_blend_tx))
    specular_blend_tx.attrs.input1[0] = specular_multiplier
    specular_blend_tx.attrs.input1[1] = specular_multiplier
    specular_blend_tx.attrs.input1[2] = specular_multiplier
    specular_blend_tx.attrs.mode = 8

    connected_attrs = ix.api.OfAttrVector()
    get_attrs_connected_to_texture(specular_tx, connected_attrs, ix=ix)
    for i_attr in range(0, connected_attrs.get_count()):
        logging.debug("Replace attr: " + str(connected_attrs[i_attr]))
        ix.cmds.SetTexture([str(connected_attrs[i_attr])], str(specular_blend_tx))
    ix.cmds.SetTexture([str(specular_blend_tx) + ".input2"], str(specular_tx))

    # Setup roughness blend
    logging.debug("Setup roughness blend")
    roughness_blend_tx = ix.cmds.CreateObject(surface_name + MOISTURE_ROUGHNESS_BLEND_SUFFIX, "TextureBlend", "Global",
                                              str(ctx))
    ix.cmds.SetTexture([str(roughness_blend_tx) + ".mix"], str(multi_blend_tx))
    roughness_blend_tx.attrs.input1[0] = roughness_multiplier
    roughness_blend_tx.attrs.input1[1] = roughness_multiplier
    roughness_blend_tx.attrs.input1[2] = roughness_multiplier
    roughness_blend_tx.attrs.mode = 7

    connected_attrs = ix.api.OfAttrVector()
    get_attrs_connected_to_texture(roughness_tx, connected_attrs, ix=ix)
    for i_attr in range(0, connected_attrs.get_count()):
        logging.debug("Replace attr: " + str(connected_attrs[i_attr]))
        ix.cmds.SetTexture([str(connected_attrs[i_attr])], str(roughness_blend_tx))
    ix.cmds.SetTexture([str(roughness_blend_tx) + ".input2"], str(roughness_tx))

    # Setup IOR blend
    ior_tx = ix.cmds.CreateObject(surface_name + MOISTURE_IOR_BLEND_SUFFIX, "TextureBlend", "Global", str(ctx))
    ior_tx.attrs.input2[0] = DEFAULT_IOR
    ior_tx.attrs.input2[1] = DEFAULT_IOR
    ior_tx.attrs.input2[2] = DEFAULT_IOR
    ior_tx.attrs.input1[0] = ior
    ior_tx.attrs.input1[1] = ior
    ior_tx.attrs.input1[2] = ior
    ix.cmds.SetTexture([str(ior_tx) + ".mix"], str(multi_blend_tx))
    logging.debug("Attaching IOR")
    ix.cmds.SetTexture([str(mtl) + ".specular_1_index_of_refraction"], str(ior_tx))
    logging.debug("Done moistening!!!")


def tint_surface(ctx, color, strength=.5, **kwargs):
    """
    Tints the diffuse texture with the specified color
    """
    logging.debug("Tint surface started")
    ix = get_ix(kwargs.get("ix"))
    if not check_context(ctx, ix=ix):
        return None

    objects_array = ix.api.OfObjectArray(ctx.get_object_count())
    flags = ix.api.CoreBitFieldHelper()
    ctx.get_all_objects(objects_array, flags, False)
    surface_name = os.path.basename(str(ctx))
    mtl = None
    for ctx_member in objects_array:
        if check_selection([ctx_member], is_kindof=["MaterialPhysicalStandard", ], max_num=1):
            if ctx_member.is_local() or not mtl:
                mtl = ctx_member
    if not mtl:
        ix.log_warning("No valid material or displacement found.")
        return False

    diffuse_tx = ix.get_item(str(mtl) + '.diffuse_front_color').get_texture()
    if diffuse_tx:
        tint_tx = ix.cmds.CreateObject(surface_name + DIFFUSE_TINT_SUFFIX, "TextureBlend", "Global", str(ctx))
        tint_tx.attrs.mix = strength
        tint_tx.attrs.mode = 12
        tint_tx.attrs.input1[0] = color[0]
        tint_tx.attrs.input1[1] = color[1]
        tint_tx.attrs.input1[2] = color[2]
        ix.cmds.SetTexture([str(tint_tx) + ".input2"], str(diffuse_tx))
        ix.cmds.SetTexture([str(mtl) + ".diffuse_front_color"], str(tint_tx))
        logging.debug("Tint succeeded!!!")
        return tint_tx
    else:
        ix.log_warning("No textures assigned to diffuse channel.")
        logging.debug("No textures assigned to diffuse channel.")
        return None


def replace_surface(ctx, surface_directory, ior=DEFAULT_IOR, projection_type="triplanar", object_space=0,
                    clip_opacity=True, srgb=(), triplanar_blend=0.5, **kwargs):
    """
    Replace the selected surface context with a different surface.
    Links between blend materials are maintained.
    """
    logging.debug("Replace surface called")
    ix = get_ix(kwargs.get("ix"))
    if not check_context(ctx, ix=ix):
        return None

    surface_directory = os.path.normpath(surface_directory)
    if not os.path.isdir(surface_directory):
        return ix.log_warning("Invalid directory specified: " + surface_directory)
    logging.debug("Surface directory:" + surface_directory)

    # Initial data
    json_data = get_json_data_from_directory(surface_directory)
    if not json_data:
        ix.log_warning("Could not find a Megascans JSON file. Defaulting to standard settings.")
    logging.debug("JSON data:")
    logging.debug(str(json_data))
    surface_height = json_data.get('surface_height', DEFAULT_DISPLACEMENT_HEIGHT)
    logging.debug("Surface height:" + str(surface_height))
    scan_area = json_data.get('scan_area', DEFAULT_UV_SCALE)
    logging.debug("Scan area:" + str(scan_area))
    tileable = json_data.get('tileable', True)
    surface_name = os.path.basename(os.path.normpath(surface_directory))
    logging.debug("Surface name:" + str(surface_name))

    # Let's find the textures
    textures = get_textures_from_directory(surface_directory)
    streamed_maps = get_stream_map_files(textures)
    if not textures:
        ix.log_warning("No textures found in directory.")
        return False

    surface = Surface(ix)
    surface.load(ctx)
    update_textures = {}
    for key, tx in surface.textures.copy().iteritems():
        if tx.is_kindof('TextureMapFile') or tx.is_kindof('TextureStreamedMapFile'):
            # Swap filename
            if key in textures:
                print "UPDATING FROM SURFACE: " + key
                logging.debug("Texture needing update: " + key)
                update_textures[key] = textures.get(key)
            elif key not in textures:
                print "DELETING FROM SURFACE: " + key
                logging.debug("Texture no longer needed: " + key)
                surface.destroy_tx(key)
    new_textures = {}
    for key, tx in textures.iteritems():
        if key not in surface.textures:
            if (key == 'gloss' and 'roughness' in surface.textures) or \
                    (key == 'roughness' and 'gloss' in surface.textures):
                continue
            if (key == 'normal' and 'bump' in surface.textures) or \
                    (key == 'bump' and 'normal' in surface.textures):
                continue
            print "NOT IN SURFACE: " + key
            logging.debug("New texture: " + key)
            new_textures[key] = tx

    surface.create_textures(new_textures, srgb=srgb, streamed_maps=streamed_maps, clip_opacity=clip_opacity)
    surface.update_ior(ior)
    surface.update_textures(update_textures, srgb, streamed_maps=streamed_maps)
    surface.update_names(surface_name)
    surface.update_displacement(surface_height)
    surface.update_opacity(clip_opacity=clip_opacity, found_textures=textures, update_textures=update_textures)
    surface.update_projection(projection=projection_type, uv_scale=scan_area,
                              triplanar_blend=triplanar_blend, object_space=object_space, tile=True)
    surface.clean()
    return surface


def mix_surfaces(srf_ctxs, cover_ctx, mix_name="mix" + MATERIAL_SUFFIX,
                 target_context=None, displacement_blend=True, height_blend=False,
                 ao_blend=False, fractal_blend=True, triplanar_blend=True,
                 slope_blend=True, scope_blend=True, assign_mtls=True, **kwargs):
    """Mixes one or multiple surfaces with a cover surface."""
    ix = get_ix(kwargs.get("ix"))
    if not target_context:
        target_context = ix.application.get_working_context()
    if not check_context(target_context, ix=ix):
        return None
    print "Mixing surfaces"
    logging.debug("Mixing surfaces...")

    root_ctx = ix.cmds.CreateContext(mix_name, "Global", str(target_context))
    selectors_ctx = ix.cmds.CreateContext(MIX_SELECTORS_NAME, "Global", str(root_ctx))

    cover_mtl = get_mtl_from_context(cover_ctx, ix=ix)
    cover_disp = get_disp_from_context(cover_ctx, ix=ix)
    cover_name = cover_ctx.get_name()
    logging.debug("Cover mtl: " + cover_name)
    logging.debug("Setting up common selectors...")
    # Setup all common selectors
    # Setup fractal noise
    fractal_selector = create_fractal_selector(selectors_ctx, mix_name, MIX_SUFFIX, ix=ix)

    # Setup slope gradient
    slope_selector = create_slope_selector(selectors_ctx, mix_name, MIX_SUFFIX, ix=ix)

    # Setup scope
    scope_selector = create_scope_selector(selectors_ctx, mix_name, MIX_SUFFIX, ix=ix)

    # Setup triplanar
    triplanar_selector = create_triplanar_selector(selectors_ctx, mix_name, MIX_SUFFIX, ix=ix)

    # Setup AO
    ao_selector = create_ao_selector(selectors_ctx, mix_name, MIX_SUFFIX, ix=ix)

    # Setup height blend
    height_selector = create_height_selector(selectors_ctx, mix_name, MIX_SUFFIX, ix=ix)

    # Put all selectors in a TextureMultiBlend
    logging.debug("Generate master multi blend and attach selectors: ")
    multi_blend_tx = ix.cmds.CreateObject(mix_name + MULTI_BLEND_SUFFIX, "TextureMultiBlend",
                                          "Global", str(root_ctx))
    multi_blend_tx.attrs.layer_1_label[0] = "Base intensity"
    # Attach displacement blend
    multi_blend_tx.attrs.enable_layer_2 = True
    multi_blend_tx.attrs.layer_2_label[0] = "Displacement Blend"
    multi_blend_tx.attrs.layer_2_mode = 1
    # Attach Ambient Occlusion blend
    multi_blend_tx.attrs.enable_layer_3 = True
    multi_blend_tx.attrs.layer_3_mode = 1
    multi_blend_tx.attrs.layer_3_label[0] = "Ambient Occlusion Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_3_color"], str(ao_selector))
    if not ao_blend: multi_blend_tx.attrs.enable_layer_3 = False
    # Attach height blend
    multi_blend_tx.attrs.enable_layer_4 = True
    multi_blend_tx.attrs.layer_4_mode = 1
    multi_blend_tx.attrs.layer_4_label[0] = "Height Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_4_color"], str(height_selector))
    if not height_blend: multi_blend_tx.attrs.enable_layer_4 = False
    # Attach slope blend
    multi_blend_tx.attrs.enable_layer_5 = True
    multi_blend_tx.attrs.layer_5_mode = 1
    multi_blend_tx.attrs.layer_5_label[0] = "Slope Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_5_color"], str(slope_selector))
    if not slope_blend: multi_blend_tx.attrs.enable_layer_5 = False
    # Attach triplanar blend
    multi_blend_tx.attrs.enable_layer_6 = True
    multi_blend_tx.attrs.layer_6_mode = 1
    multi_blend_tx.attrs.layer_6_label[0] = "Triplanar Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_6_color"], str(triplanar_selector))
    if not triplanar_blend: multi_blend_tx.attrs.enable_layer_6 = False
    # Attach scope blend
    multi_blend_tx.attrs.enable_layer_7 = True
    multi_blend_tx.attrs.layer_7_mode = 1
    multi_blend_tx.attrs.layer_7_label[0] = "Scope Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_7_color"], str(scope_selector))
    if not scope_blend: multi_blend_tx.attrs.enable_layer_7 = False
    # Attach fractal blend
    multi_blend_tx.attrs.enable_layer_8 = True
    multi_blend_tx.attrs.layer_8_label[0] = "Fractal Blend"
    multi_blend_tx.attrs.layer_8_mode = 4 if True in [ao_blend, height_blend, slope_blend, scope_blend] else 1
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_8_color"], str(fractal_selector))
    if not fractal_blend: multi_blend_tx.attrs.enable_layer_8 = False

    # Set up each surface mix
    for srf_ctx in srf_ctxs:
        mix_srf_name = srf_ctx.get_name()
        logging.debug("Generating mix of base surface: " + mix_srf_name)
        mix_ctx = ix.cmds.CreateContext(mix_srf_name + MIX_SUFFIX, "Global", str(root_ctx))
        mix_selectors_ctx = ix.cmds.CreateContext("custom_selectors", "Global", str(mix_ctx))

        base_mtl = get_mtl_from_context(srf_ctx, ix=ix)
        base_disp = get_disp_from_context(srf_ctx, ix=ix)

        has_displacement = base_disp and cover_disp

        mix_multi_blend_tx = ix.cmds.Instantiate([str(multi_blend_tx)])[0]
        ix.cmds.MoveItemsTo([str(mix_multi_blend_tx)], mix_selectors_ctx)
        ix.cmds.RenameItem(str(mix_multi_blend_tx), mix_srf_name + MULTI_BLEND_SUFFIX)
        # Blend materials
        mix_mtl = ix.cmds.CreateObject(mix_srf_name + MIX_SUFFIX + MATERIAL_SUFFIX, "MaterialPhysicalBlend", "Global",
                                       str(mix_ctx))
        ix.cmds.SetTexture([str(mix_mtl) + ".mix"], str(mix_multi_blend_tx))
        ix.cmds.SetValue(str(mix_mtl) + ".input2", [str(base_mtl)])
        ix.cmds.SetValue(str(mix_mtl) + ".input1", [str(cover_mtl)])

        if has_displacement:
            logging.debug("Surface has displacement. Setting up unique selector...")
            ix.cmds.LocalizeAttributes([str(mix_multi_blend_tx) + ".layer_2_color",
                                        str(mix_multi_blend_tx) + ".enable_layer_2"], True)
            # Setup displacements for height blending.
            # Base surface
            print "Setting up surface 1"
            base_srf_height = base_disp.attrs.front_value[0]
            print "Base surface height: " + str(base_srf_height)
            base_disp_tx_front_value = ix.get_item(str(base_disp) + ".front_value")
            base_disp_tx = base_disp_tx_front_value.get_texture()
            base_disp_height_scale_tx = ix.cmds.CreateObject(mix_srf_name + DISPLACEMENT_HEIGHT_SCALE_SUFFIX,
                                                             "TextureMultiply", "Global", str(mix_selectors_ctx))
            ix.cmds.SetTexture([str(base_disp_height_scale_tx) + ".input1"], str(base_disp_tx))

            base_disp_height_scale_tx.attrs.input2[0] = base_srf_height
            base_disp_height_scale_tx.attrs.input2[1] = base_srf_height
            base_disp_height_scale_tx.attrs.input2[2] = base_srf_height
            base_disp_blend_offset_tx = ix.cmds.CreateObject(mix_srf_name + DISPLACEMENT_BLEND_OFFSET_SUFFIX,
                                                             "TextureAdd", "Global", str(mix_selectors_ctx))
            ix.cmds.SetTexture([str(base_disp_blend_offset_tx) + ".input1"], str(base_disp_height_scale_tx))
            base_disp_offset_tx = ix.cmds.CreateObject(mix_srf_name + DISPLACEMENT_OFFSET_SUFFIX, "TextureAdd",
                                                       "Global", str(mix_selectors_ctx))
            base_disp_offset_tx.attrs.input2[0] = (base_srf_height / 2) * -1
            base_disp_offset_tx.attrs.input2[1] = (base_srf_height / 2) * -1
            base_disp_offset_tx.attrs.input2[2] = (base_srf_height / 2) * -1
            ix.cmds.SetTexture([str(base_disp_offset_tx) + ".input1"], str(base_disp_height_scale_tx))

            # Surface 2
            print "Setting up surface 2"
            cover_srf_height = cover_disp.attrs.front_value[0]
            print "Surface 2 height: " + str(cover_srf_height)
            cover_disp_tx_front_value = ix.get_item(str(cover_disp) + ".front_value")
            cover_disp_tx = cover_disp_tx_front_value.get_texture()
            cover_disp_height_scale_tx = ix.cmds.CreateObject(cover_name + DISPLACEMENT_HEIGHT_SCALE_SUFFIX,
                                                              "TextureMultiply", "Global", str(mix_selectors_ctx))
            ix.cmds.SetTexture([str(cover_disp_height_scale_tx) + ".input1"], str(cover_disp_tx))
            cover_disp_height_scale_tx.attrs.input2[0] = cover_srf_height
            cover_disp_height_scale_tx.attrs.input2[1] = cover_srf_height
            cover_disp_height_scale_tx.attrs.input2[2] = cover_srf_height
            cover_disp_blend_offset_tx = ix.cmds.CreateObject(cover_name + DISPLACEMENT_BLEND_OFFSET_SUFFIX,
                                                              "TextureAdd", "Global", str(mix_selectors_ctx))
            ix.cmds.SetTexture([str(cover_disp_blend_offset_tx) + ".input1"], str(cover_disp_height_scale_tx))
            cover_disp_offset_tx = ix.cmds.CreateObject(cover_name + DISPLACEMENT_OFFSET_SUFFIX, "TextureAdd",
                                                        "Global", str(mix_selectors_ctx))
            cover_disp_offset_tx.attrs.input2[0] = (base_srf_height / 2) * -1
            cover_disp_offset_tx.attrs.input2[1] = (base_srf_height / 2) * -1
            cover_disp_offset_tx.attrs.input2[2] = (base_srf_height / 2) * -1
            ix.cmds.SetTexture([str(cover_disp_offset_tx) + ".input1"], str(cover_disp_height_scale_tx))

            disp_branch_selector = ix.cmds.CreateObject(mix_srf_name + DISPLACEMENT_BRANCH_SUFFIX, "TextureBranch",
                                                        "Global", str(mix_selectors_ctx))

            ix.cmds.SetTexture([str(disp_branch_selector) + ".input_a"], str(base_disp_blend_offset_tx))
            ix.cmds.SetTexture([str(disp_branch_selector) + ".input_b"], str(cover_disp_blend_offset_tx))
            disp_branch_selector.attrs.mode = 2

            # Hook to multiblend instance
            ix.cmds.SetTexture([str(mix_multi_blend_tx) + ".layer_2_color"], str(disp_branch_selector))
            if not displacement_blend: mix_multi_blend_tx.attrs.enable_layer_2 = False
            # Finalize new Displacement map
            disp_multi_blend_tx = ix.cmds.CreateObject(mix_srf_name + DISPLACEMENT_BLEND_SUFFIX,
                                                       "TextureMultiBlend", "Global", str(mix_selectors_ctx))
            ix.cmds.SetTexture([str(disp_multi_blend_tx) + ".layer_1_color"], str(base_disp_offset_tx))
            disp_multi_blend_tx.attrs.enable_layer_2 = True
            disp_multi_blend_tx.attrs.layer_2_label[0] = "Mix mode"
            ix.cmds.SetTexture([str(disp_multi_blend_tx) + ".layer_2_color"], str(cover_disp_offset_tx))
            ix.cmds.SetTexture([str(disp_multi_blend_tx) + ".layer_2_mix"], str(mix_multi_blend_tx))
            disp_multi_blend_tx.attrs.enable_layer_3 = True
            disp_multi_blend_tx.attrs.layer_3_label[0] = "Add mode"
            ix.cmds.SetTexture([str(disp_multi_blend_tx) + ".layer_3_color"], str(cover_disp_offset_tx))
            ix.cmds.SetTexture([str(disp_multi_blend_tx) + ".layer_3_mix"], str(mix_multi_blend_tx))
            disp_multi_blend_tx.attrs.layer_3_mode = 6
            disp_multi_blend_tx.attrs.enable_layer_3 = False

            displacement_map = ix.cmds.CreateObject(mix_srf_name + DISPLACEMENT_MAP_SUFFIX, "Displacement",
                                                    "Global",
                                                    str(mix_ctx))
            displacement_map.attrs.bound[0] = 1
            displacement_map.attrs.bound[1] = 1
            displacement_map.attrs.bound[2] = 1
            displacement_map.attrs.front_value = 1
            ix.cmds.SetTexture([str(displacement_map) + ".front_value"], str(disp_multi_blend_tx))
        if assign_mtls:
            logging.debug("Material assignment...")
            ix.selection.deselect_all()
            ix.application.check_for_events()
            ix.selection.select(base_mtl)
            ix.application.select_next_outputs()
            selection = [i for i in ix.selection]
            for sel in selection:
                if sel.is_kindof("Geometry"):
                    shading_group = sel.get_module().get_geometry().get_shading_group_names()
                    count = shading_group.get_count()
                    for j in range(count):
                        shaders = sel.attrs.materials[j]
                        if shaders == base_mtl:
                            ix.cmds.SetValues([str(sel) + ".materials" + str([j])], [str(mix_mtl)])
            ix.selection.deselect_all()
            ix.application.check_for_events()
            logging.debug("... done material assignment.")
    logging.debug("Done mixing!!!")
    return root_ctx


def toggle_surface_complexity(ctx, **kwargs):
    """Temporarily replaces the current surface with a much simpeler MaterialPhysicalDiffuse material."""
    logging.debug("Toggle surface complexity...")
    ix = get_ix(kwargs.get("ix"))
    objects_array = ix.api.OfObjectArray(ctx.get_object_count())
    flags = ix.api.CoreBitFieldHelper()
    ctx.get_all_objects(objects_array, flags, False)
    surface_name = os.path.basename(str(ctx))

    mtl = None
    preview_mtl = None
    disp = None
    for ctx_member in objects_array:
        if ctx_member.is_kindof("MaterialPhysicalStandard"):
            if ctx_member.is_local() or not mtl:
                mtl = ctx_member
        if ctx_member.is_kindof("MaterialPhysicalBlend"):
            mtl = ctx_member
        if ctx_member.is_kindof("MaterialPhysicalDiffuse"):
            preview_mtl = ctx_member
        if ctx_member.is_kindof("Displacement"):
            disp = ctx_member
    if not mtl:
        ix.log_warning("No MaterialPhysicalStandard found in context.")
        ix.selection.deselect_all()
        return False
    if disp:
        # Disable the displacement
        ix.cmds.DisableItems([str(disp)], disp.is_enabled())
    if mtl.is_kindof("MaterialPhysicalBlend"):
        ix.selection.deselect_all()
        return True
    if not preview_mtl:
        logging.debug("Switching to simple mode...")
        diffuse_tx = ix.get_item(str(mtl) + '.diffuse_front_color').get_texture()
        new_preview_mtl = ix.cmds.CreateObject(surface_name + PREVIEW_MATERIAL_SUFFIX, "MaterialPhysicalDiffuse",
                                               "Global", str(ctx))
        ix.cmds.SetTexture([new_preview_mtl.get_full_name() + ".front_color"],
                           str(diffuse_tx))
        connected_attrs = ix.api.OfAttrVector()
        get_attrs_connected_to_texture(mtl, connected_attrs, ix=ix)
        for i in range(0, connected_attrs.get_count()):
            print connected_attrs[i]
            ix.cmds.SetValues([connected_attrs[i].get_full_name()], [str(new_preview_mtl)])
        ix.selection.select(mtl)
        ix.application.select_next_outputs()
        for sel in ix.selection:
            if sel.is_kindof("Geometry"):
                shading_group = sel.get_module().get_geometry().get_shading_group_names()
                count = shading_group.get_count()
                for j in range(count):
                    shaders = sel.attrs.materials[j]
                    if shaders == mtl:
                        ix.cmds.SetValues([sel.get_full_name() + ".materials" + str([j])], [str(new_preview_mtl)])
    else:
        logging.debug("Reverting back to complex mode...")
        connected_attrs = ix.api.OfAttrVector()
        get_attrs_connected_to_texture(preview_mtl, connected_attrs, ix=ix)
        for i in range(0, connected_attrs.get_count()):
            print connected_attrs[i]
            ix.cmds.SetValues([connected_attrs[i].get_full_name()], [mtl.get_full_name()])
        ix.selection.select(preview_mtl)
        ix.application.select_next_outputs()
        for sel in ix.selection:
            if sel.is_kindof("Geometry"):
                shading_group = sel.get_module().get_geometry().get_shading_group_names()
                count = shading_group.get_count()
                for j in range(count):
                    shaders = sel.attrs.materials[j]
                    if shaders == preview_mtl:
                        ix.cmds.SetValues([sel.get_full_name() + ".materials" + str([j])], [str(mtl)])
        ix.cmds.DeleteItems([preview_mtl.get_full_name()])
    ix.selection.deselect_all()
    logging.debug("Done toggling surface complexity!!!")


def tx_to_triplanar(tx, blend=0.5, object_space=0, **kwargs):
    """Converts the texture to triplanar."""
    logging.debug("Converting texture to triplanar: " + str(tx))
    ix = get_ix(kwargs.get("ix"))
    print "Triplanar Blend: " + str(blend)
    ctx = tx.get_context()
    triplanar = ix.cmds.CreateObject(tx.get_contextual_name() + TRIPLANAR_SUFFIX, "TextureTriplanar", "Global",
                                     str(ctx))
    connected_attrs = ix.api.OfAttrVector()

    get_attrs_connected_to_texture(tx, connected_attrs, ix=ix)

    for i_attr in range(0, connected_attrs.get_count()):
        ix.cmds.SetTexture([str(connected_attrs[i_attr])], str(triplanar))
    ix.cmds.SetTexture([str(triplanar) + ".right"], str(tx))
    ix.cmds.SetTexture([str(triplanar) + ".left"], str(tx))
    ix.cmds.SetTexture([str(triplanar) + ".top"], str(tx))
    ix.cmds.SetTexture([str(triplanar) + ".bottom"], str(tx))
    ix.cmds.SetTexture([str(triplanar) + ".front"], str(tx))
    ix.cmds.SetTexture([str(triplanar) + ".back"], str(tx))
    ix.cmds.SetValues([str(triplanar) + '.blend', str(triplanar) + '.object_space'],
                      [str(blend), str(object_space)])
    return triplanar


def blur_tx(tx, radius=0.01, quality=DEFAULT_BLUR_QUALITY, **kwargs):
    """Blurs the texture."""
    logging.debug("Blurring selected texture: " + str(tx))
    ix = get_ix(kwargs.get("ix"))
    ctx = tx.get_context()
    blur = ix.cmds.CreateObject(tx.get_contextual_name() + BLUR_SUFFIX, "TextureBlur", "Global", str(ctx))

    connected_attrs = ix.api.OfAttrVector()

    get_attrs_connected_to_texture(tx, connected_attrs, ix=ix)

    for i_attr in range(0, connected_attrs.get_count()):
        ix.cmds.SetTexture([connected_attrs[i_attr].get_full_name()], blur.get_full_name())
    ix.cmds.SetTexture([str(blur) + ".color"], str(tx))
    blur.attrs.radius = radius
    blur.attrs.quality = quality
    return blur


def generate_decimated_pointcloud(geometry, ctx=None,
                                  pc_type="GeometryPointCloud",
                                  use_density=False,
                                  density=.1,
                                  point_count=10000,
                                  height_blend=False,
                                  fractal_blend=False,
                                  scope_blend=False,
                                  slope_blend=True,
                                  triplanar_blend=False,
                                  ao_blend=False,
                                  **kwargs):
    """Generates a pointcloud from the selected geometry."""
    logging.debug("Generating decimated pointcloud...")
    logging.debug("Type: " + pc_type)
    logging.debug("Use density: " + str(use_density))
    ix = get_ix(kwargs.get("ix"))
    if not ctx:
        ctx = ix.application.get_working_context()
    if not check_context(ctx, ix=ix):
        return None

    geo_name = geometry.get_contextual_name()
    pc = ix.cmds.CreateObject(geo_name + POINTCLOUD_SUFFIX, pc_type, "Global", str(ctx))
    ix.application.check_for_events()
    if pc_type == "GeometryPointCloud":
        if use_density:
            ix.cmds.SetValue(str(pc) + ".use_density", [str(1)])
            ix.application.check_for_events()
            ix.cmds.SetValue(str(pc) + ".density", [str(density)])
        else:
            pc.attrs.point_count = int(point_count)
    else:
        pc.attrs.point_count = int(point_count)
    logging.debug("Setting up multi blend and selectors...")
    multi_blend_tx = ix.cmds.CreateObject(geo_name + DECIMATE_SUFFIX + MULTI_BLEND_SUFFIX, "TextureMultiBlend",
                                          "Global", str(ctx))
    # Setup fractal noise
    fractal_selector = create_fractal_selector(ctx, geo_name, DECIMATE_SUFFIX, ix=ix)

    # Setup slope gradient
    slope_selector = create_slope_selector(ctx, geo_name, DECIMATE_SUFFIX, ix=ix)

    # Setup scope
    scope_selector = create_scope_selector(ctx, geo_name, DECIMATE_SUFFIX, ix=ix)

    # Setup triplanar
    triplanar_selector = create_triplanar_selector(ctx, geo_name, DECIMATE_SUFFIX, ix=ix)

    # Setup AO
    ao_selector = create_ao_selector(ctx, geo_name, DECIMATE_SUFFIX, ix=ix)

    # Setup height blend
    height_selector = create_height_selector(ctx, geo_name, DECIMATE_SUFFIX, ix=ix)

    multi_blend_tx.attrs.layer_1_label[0] = "Base intensity"
    # Attach Ambient Occlusion blend
    multi_blend_tx.attrs.enable_layer_2 = True
    multi_blend_tx.attrs.layer_2_mode = 1
    multi_blend_tx.attrs.layer_2_label[0] = "Ambient Occlusion Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_2_color"], str(ao_selector))
    if not ao_blend: multi_blend_tx.attrs.enable_layer_2 = False
    # Attach height blend
    multi_blend_tx.attrs.enable_layer_4 = True
    multi_blend_tx.attrs.layer_4_mode = 1
    multi_blend_tx.attrs.layer_4_label[0] = "Height Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_4_color"], str(height_selector))
    if not height_blend: multi_blend_tx.attrs.enable_layer_4 = False
    # Attach slope blend
    multi_blend_tx.attrs.enable_layer_5 = True
    multi_blend_tx.attrs.layer_5_mode = 1
    multi_blend_tx.attrs.layer_5_label[0] = "Slope Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_5_color"], str(slope_selector))
    if not slope_blend: multi_blend_tx.attrs.enable_layer_5 = False
    # Attach triplanar blend
    multi_blend_tx.attrs.enable_layer_6 = True
    multi_blend_tx.attrs.layer_6_mode = 1
    multi_blend_tx.attrs.layer_6_label[0] = "Triplanar Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_6_color"], str(triplanar_selector))
    if not triplanar_blend: multi_blend_tx.attrs.enable_layer_6 = False
    # Attach scope blend
    multi_blend_tx.attrs.enable_layer_7 = True
    multi_blend_tx.attrs.layer_7_mode = 1
    multi_blend_tx.attrs.layer_7_label[0] = "Scope Blend"
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_7_color"], str(scope_selector))
    if not scope_blend: multi_blend_tx.attrs.enable_layer_7 = False
    # Attach fractal blend
    multi_blend_tx.attrs.enable_layer_8 = True
    multi_blend_tx.attrs.layer_8_label[0] = "Fractal Blend"
    multi_blend_tx.attrs.layer_8_mode = 4 if True in [ao_blend, height_blend, slope_blend, scope_blend] else 1
    ix.cmds.SetTexture([str(multi_blend_tx) + ".layer_8_color"], str(fractal_selector))
    if not fractal_blend: multi_blend_tx.attrs.enable_layer_8 = False

    if pc_type == "GeometryPointCloud":
        ix.cmds.SetValue(str(pc) + ".decimate_texture", [str(multi_blend_tx)])
        ix.cmds.SetValue(str(multi_blend_tx) + ".invert", [str(1)])
    else:
        ix.cmds.SetValue(str(pc) + ".texture", [str(multi_blend_tx)])

    ix.cmds.SetValue(str(pc) + ".geometry", [str(geometry)])
    logging.debug("Done generating point cloud!!!")
    return pc


def import_ms_library(library_dir, target_ctx=None, custom_assets=True, skip_categories=(), **kwargs):
    """Imports the whole Megascans Library. Point it to the Downloaded folder inside your library folder.
    """
    logging.debug("Importing Megascans library...")

    ix = get_ix(kwargs.get("ix"))
    if not target_ctx:
        target_ctx = ix.application.get_working_context()
    if not check_context(target_ctx, ix=ix):
        return None
    if not os.path.isdir(library_dir):
        return None
    if os.path.isdir(os.path.join(library_dir, "Downloaded")):
        library_dir = os.path.join(library_dir, "Downloaded")
    logging.debug("Directory set to: " + library_dir)
    print "Scanning folders in " + library_dir

    for category_dir_name in os.listdir(library_dir):
        category_dir_path = os.path.join(library_dir, category_dir_name)
        logging.debug("Checking if directory contains matches keywords: " + category_dir_name)
        if category_dir_name in ["3d", "3dplant", "surface", "surfaces", "atlas", "atlases"]:
            if category_dir_name not in skip_categories and os.path.isdir(category_dir_path):
                context_name = category_dir_name
                if os.path.basename(library_dir) == "My Assets" and category_dir_name == "surfaces":
                    context_name = LIBRARY_MIXER_CTX
                ctx = ix.item_exists(str(target_ctx) + "/" + MEGASCANS_LIBRARY_CATEGORY_PREFIX + context_name)
                if not ctx:
                    ctx = ix.cmds.CreateContext(MEGASCANS_LIBRARY_CATEGORY_PREFIX + context_name,
                                                "Global", str(target_ctx))
                print "Importing library folder: " + category_dir_name
                for asset_directory_name in os.listdir(category_dir_path):
                    asset_directory_path = os.path.join(category_dir_path, asset_directory_name)
                    if os.path.isdir(asset_directory_path):
                        if not ix.item_exists(str(ctx) + "/" + asset_directory_name):
                            print "Importing asset: " + asset_directory_path
                            import_asset(asset_directory_path, target_ctx=ctx, srgb=MEGASCANS_SRGB_TEXTURES, ix=ix)
    if custom_assets and os.path.isdir(os.path.join(library_dir, "My Assets")):
        logging.debug("My Assets exists...")
        import_ms_library(os.path.join(library_dir, "My Assets"), target_ctx=target_ctx,
                          skip_categories=skip_categories, custom_assets=False, ix=ix)
