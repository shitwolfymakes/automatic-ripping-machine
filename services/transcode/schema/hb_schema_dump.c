/* hb_schema_dump: print the HandBrake preset schema as one JSON document.
 *
 * Built and run in the transcode image's handbrake-builder stage, linked
 * against the same libhandbrake.a as HandBrakeCLI, so the schema and the
 * binary cannot disagree. Usage: hb_schema_dump <handbrake-tag> > schema.json
 *
 * Only public libhb API is used. Traps (see the #601 design spec, 4.1):
 *   - hb_video_encoder_get_next() lists only the encoders enabled on this
 *     machine, so the codec id space is walked through
 *     hb_video_encoder_get_from_codec() instead.
 *   - hb_filter_get_tunes_short_name() segfaults for a filter with no tunes;
 *     hb_filter_param_get_tunes() is used instead.
 *   - hb_get_version() is a snapshot string in a shallow tag clone, so the
 *     tag comes from argv[1] (the HANDBRAKE_VERSION build arg).
 *   - hb_video_quality_get_limits() leaves its outputs untouched for QSV
 *     without an adapter; that encoder's quality is emitted as null.
 *
 * Exits non-zero when any list comes out empty.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "handbrake/handbrake.h"

#define SCHEMA_FORMAT 1

/* The low byte(s) of a video codec id, OR'd with any subset of these masks,
 * covers every HB_VCODEC_* define. */
#define VCODEC_LOW_ID_LIMIT 0x400
static const int vcodec_masks[] = {
    HB_VCODEC_AV1_MASK,     HB_VCODEC_H264_MASK, HB_VCODEC_H265_MASK,
    HB_VCODEC_SVT_AV1_MASK, HB_VCODEC_X264_MASK, HB_VCODEC_X265_MASK,
    HB_VCODEC_VT_MASK,      HB_VCODEC_QSV_MASK,  HB_VCODEC_FFMPEG_MASK,
};
#define VCODEC_MASK_COUNT ((int)(sizeof(vcodec_masks) / sizeof(vcodec_masks[0])))

/* Filters with presets, keyed by the short name presets use for them
 * (PictureDenoiseFilter: "nlmeans", PictureDeinterlaceFilter: "decomb", ...). */
typedef struct {
    int id;
    const char *name;
} filter_entry_t;

static const filter_entry_t filters[] = {
    {HB_FILTER_DETELECINE, "detelecine"},
    {HB_FILTER_COMB_DETECT, "comb_detect"},
    {HB_FILTER_DECOMB, "decomb"},
    {HB_FILTER_YADIF, "yadif"},
    {HB_FILTER_BWDIF, "bwdif"},
    {HB_FILTER_DEBLOCK, "deblock"},
    {HB_FILTER_HQDN3D, "hqdn3d"},
    {HB_FILTER_NLMEANS, "nlmeans"},
    {HB_FILTER_CHROMA_SMOOTH, "chroma_smooth"},
    {HB_FILTER_LAPSHARP, "lapsharp"},
    {HB_FILTER_UNSHARP, "unsharp"},
    {HB_FILTER_COLORSPACE, "colorspace"},
};
#define FILTER_COUNT ((int)(sizeof(filters) / sizeof(filters[0])))

static void fail(const char *what)
{
    fprintf(stderr, "hb_schema_dump: %s\n", what);
    exit(1);
}

static hb_value_t *require_items(hb_value_t *array, const char *what)
{
    if (hb_value_array_len(array) == 0)
    {
        fail(what);
    }
    return array;
}

static hb_value_t *string_list(const char *const *names)
{
    hb_value_t *array = hb_value_array_init();
    for (int i = 0; names != NULL && names[i] != NULL; i++)
    {
        hb_value_array_append(array, hb_value_string(names[i]));
    }
    return array;
}

/* libhb's limits are floats; widen them at float precision so a step of 0.1
 * prints as 0.1 rather than 0.10000000149011612. */
static hb_value_t *float_value(float value)
{
    char text[32];
    snprintf(text, sizeof(text), "%.7g", value);
    return hb_value_double(strtod(text, NULL));
}

static hb_value_t *limits_dict(float low, float high, float step)
{
    hb_dict_t *dict = hb_dict_init();
    hb_dict_set(dict, "low", float_value(low));
    hb_dict_set(dict, "high", float_value(high));
    hb_dict_set(dict, "step", float_value(step));
    return dict;
}

/* ---- preset format ---------------------------------------------------- */

static hb_value_t *preset_version(void)
{
    int major = 0, minor = 0, micro = 0;
    hb_presets_current_version(&major, &minor, &micro);
    hb_value_t *array = hb_value_array_init();
    hb_value_array_append(array, hb_value_int(major));
    hb_value_array_append(array, hb_value_int(minor));
    hb_value_array_append(array, hb_value_int(micro));
    return array;
}

/* A preset holding only PresetName comes back from hb_presets_clean() with
 * every template key at its default. */
static hb_value_t *cleaned_preset(hb_value_t *audio_list)
{
    hb_dict_t *preset = hb_dict_init();
    hb_dict_set_string(preset, "PresetName", "template");
    if (audio_list != NULL)
    {
        hb_dict_set(preset, "AudioList", audio_list);
    }
    hb_presets_clean(preset);
    return preset;
}

static hb_value_t *preset_template(void)
{
    hb_value_t *preset = cleaned_preset(NULL);
    if (hb_dict_get(preset, "VideoEncoder") == NULL)
    {
        fail("hb_presets_clean returned no template keys");
    }
    return preset;
}

/* An empty AudioList item is filled from the template's item. */
static hb_value_t *template_audio_item(void)
{
    hb_value_t *audio_list = hb_value_array_init();
    hb_value_array_append(audio_list, hb_dict_init());
    hb_value_t *preset = cleaned_preset(audio_list);
    hb_value_t *item = hb_value_dup(hb_value_array_get(hb_dict_get(preset, "AudioList"), 0));
    hb_value_free(&preset);
    if (hb_dict_get(item, "AudioEncoder") == NULL)
    {
        fail("hb_presets_clean returned no AudioList item keys");
    }
    return item;
}

/* ---- video encoders --------------------------------------------------- */

static hb_value_t *video_quality(int codec)
{
    float low = NAN, high = NAN, step = NAN;
    int direction = 0;
    hb_video_quality_get_limits(codec, &low, &high, &step, &direction);
    if (isnan(low) || isnan(high) || isnan(step))
    {
        return hb_value_null();
    }
    hb_value_t *quality = limits_dict(low, high, step);
    hb_dict_set_string(quality, "name", hb_video_quality_get_name(codec));
    return quality;
}

static hb_value_t *video_encoder(int codec)
{
    hb_dict_t *dict = hb_dict_init();
    hb_dict_set_string(dict, "name", hb_video_encoder_get_short_name(codec));
    hb_dict_set_int(dict, "codec_id", codec);
    hb_dict_set_int(dict, "depth", hb_video_encoder_get_depth(codec));
    hb_dict_set(dict, "presets", string_list(hb_video_encoder_get_presets(codec)));
    hb_dict_set(dict, "tunes", string_list(hb_video_encoder_get_tunes(codec)));
    hb_dict_set(dict, "profiles", string_list(hb_video_encoder_get_profiles(codec)));
    hb_dict_set(dict, "levels", string_list(hb_video_encoder_get_levels(codec)));
    hb_dict_set(dict, "quality", video_quality(codec));
    hb_dict_set_bool(dict, "multipass", hb_video_multipass_is_supported(codec, 0));
    return dict;
}

static int masks_for_subset(int subset)
{
    int masks = 0;
    for (int bit = 0; bit < VCODEC_MASK_COUNT; bit++)
    {
        if (subset & (1 << bit))
        {
            masks |= vcodec_masks[bit];
        }
    }
    return masks;
}

/* A codec id names an encoder when the table has it and a non-deprecated
 * entry gives it a name (the legacy entries share codec ids with current ones). */
static int is_video_encoder(int codec)
{
    return codec != HB_VCODEC_INVALID && hb_video_encoder_get_from_codec(codec) != NULL &&
           hb_video_encoder_get_short_name(codec) != NULL;
}

static void append_encoders_with_masks(hb_value_t *array, int masks)
{
    for (int low = 0; low < VCODEC_LOW_ID_LIMIT; low++)
    {
        if (is_video_encoder(low | masks))
        {
            hb_value_array_append(array, video_encoder(low | masks));
        }
    }
}

static hb_value_t *video_encoders(void)
{
    hb_value_t *array = hb_value_array_init();
    for (int subset = 0; subset < (1 << VCODEC_MASK_COUNT); subset++)
    {
        append_encoders_with_masks(array, masks_for_subset(subset));
    }
    return require_items(array, "no video encoders");
}

/* ---- audio ------------------------------------------------------------ */

static hb_value_t *audio_mixdowns_for(int codec)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_mixdown_t *m = hb_mixdown_get_next(NULL); m != NULL; m = hb_mixdown_get_next(m))
    {
        if (hb_mixdown_has_codec_support(m->amixdown, codec))
        {
            hb_value_array_append(array, hb_value_string(m->short_name));
        }
    }
    return array;
}

static hb_value_t *audio_samplerates_for(int codec)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_rate_t *r = hb_audio_samplerate_get_next(NULL); r != NULL; r = hb_audio_samplerate_get_next(r))
    {
        if (hb_audio_samplerate_is_supported(r->rate, codec))
        {
            hb_value_array_append(array, hb_value_int(r->rate));
        }
    }
    return array;
}

/* libhb reports an unsupported scale as low == high. */
static hb_value_t *audio_scale(float low, float high, float step, float default_value)
{
    if (low == high)
    {
        return hb_value_null();
    }
    hb_value_t *scale = limits_dict(low, high, step);
    hb_dict_set(scale, "default", float_value(default_value));
    return scale;
}

static hb_value_t *audio_quality(int codec)
{
    float low = 0, high = 0, step = 0;
    int direction = 0;
    hb_audio_quality_get_limits(codec, &low, &high, &step, &direction);
    return audio_scale(low, high, step, hb_audio_quality_get_default(codec));
}

static hb_value_t *audio_compression(int codec)
{
    float low = 0, high = 0, step = 0;
    int direction = 0;
    hb_audio_compression_get_limits(codec, &low, &high, &step, &direction);
    return audio_scale(low, high, step, hb_audio_compression_get_default(codec));
}

static hb_value_t *audio_encoder(const hb_encoder_t *encoder)
{
    hb_dict_t *dict = hb_dict_init();
    hb_dict_set_string(dict, "name", encoder->short_name);
    hb_dict_set_string(dict, "long_name", encoder->name);
    hb_dict_set_int(dict, "codec_id", encoder->codec);
    hb_dict_set(dict, "mixdowns", audio_mixdowns_for(encoder->codec));
    hb_dict_set(dict, "samplerates", audio_samplerates_for(encoder->codec));
    hb_dict_set(dict, "quality", audio_quality(encoder->codec));
    hb_dict_set(dict, "compression", audio_compression(encoder->codec));
    return dict;
}

static hb_value_t *audio_encoders(void)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_encoder_t *e = hb_audio_encoder_get_next(NULL); e != NULL; e = hb_audio_encoder_get_next(e))
    {
        hb_value_array_append(array, audio_encoder(e));
    }
    return require_items(array, "no audio encoders");
}

static hb_value_t *named_item(const char *name, const char *short_name)
{
    hb_dict_t *dict = hb_dict_init();
    hb_dict_set_string(dict, "name", short_name);
    hb_dict_set_string(dict, "long_name", name);
    return dict;
}

static hb_value_t *mixdowns(void)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_mixdown_t *m = hb_mixdown_get_next(NULL); m != NULL; m = hb_mixdown_get_next(m))
    {
        hb_value_array_append(array, named_item(m->name, m->short_name));
    }
    return require_items(array, "no mixdowns");
}

static hb_value_t *audio_bitrates(void)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_rate_t *r = hb_audio_bitrate_get_next(NULL); r != NULL; r = hb_audio_bitrate_get_next(r))
    {
        hb_value_array_append(array, hb_value_int(r->rate));
    }
    return require_items(array, "no audio bitrates");
}

static hb_value_t *audio_dithers(void)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_dither_t *d = hb_audio_dither_get_next(NULL); d != NULL; d = hb_audio_dither_get_next(d))
    {
        hb_value_array_append(array, named_item(d->description, d->short_name));
    }
    return require_items(array, "no audio dithers");
}

/* ---- video framerates, containers, filters ---------------------------- */

static hb_value_t *video_framerates(void)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_rate_t *r = hb_video_framerate_get_next(NULL); r != NULL; r = hb_video_framerate_get_next(r))
    {
        hb_dict_t *dict = hb_dict_init();
        hb_dict_set_string(dict, "name", r->name);
        hb_dict_set_int(dict, "rate", r->rate);
        hb_value_array_append(array, dict);
    }
    return require_items(array, "no video framerates");
}

static hb_value_t *containers(void)
{
    hb_value_t *array = hb_value_array_init();
    for (const hb_container_t *c = hb_container_get_next(NULL); c != NULL; c = hb_container_get_next(c))
    {
        hb_value_t *dict = named_item(c->name, c->short_name);
        hb_dict_set_string(dict, "default_extension", c->default_extension);
        hb_value_array_append(array, dict);
    }
    return require_items(array, "no containers");
}

static hb_value_t *filter_param_names(const hb_filter_param_t *params)
{
    hb_value_t *array = hb_value_array_init();
    for (int i = 0; params != NULL && params[i].name != NULL; i++)
    {
        hb_value_array_append(array, hb_value_string(params[i].short_name));
    }
    return array;
}

static hb_value_t *filter_params(int filter_id)
{
    hb_dict_t *dict = hb_dict_init();
    hb_dict_set(dict, "presets", require_items(filter_param_names(hb_filter_param_get_presets(filter_id)),
                                               "a filter has no presets"));
    hb_dict_set(dict, "tunes", filter_param_names(hb_filter_param_get_tunes(filter_id)));
    return dict;
}

static hb_value_t *filter_schema(void)
{
    hb_dict_t *dict = hb_dict_init();
    for (int i = 0; i < FILTER_COUNT; i++)
    {
        hb_dict_set(dict, filters[i].name, filter_params(filters[i].id));
    }
    return dict;
}

/* ---- built-in presets ------------------------------------------------- */

static void add_builtin_preset(hb_dict_t *by_name, const hb_value_t *preset)
{
    const char *name = hb_dict_get_string(preset, "PresetName");
    if (name == NULL || hb_dict_get(by_name, name) != NULL)
    {
        fail("a built-in preset has no name or a duplicate name");
    }
    hb_dict_set(by_name, name, hb_value_dup(preset));
}

/* Folders hold presets in ChildrenArray; flatten them to name -> preset. */
static void flatten_presets(hb_dict_t *by_name, const hb_value_t *list)
{
    int count = hb_value_array_len(list);
    for (int i = 0; i < count; i++)
    {
        hb_value_t *item = hb_value_array_get(list, i);
        if (hb_dict_get_bool(item, "Folder"))
        {
            flatten_presets(by_name, hb_dict_get(item, "ChildrenArray"));
        }
        else
        {
            add_builtin_preset(by_name, item);
        }
    }
}

static hb_value_t *builtin_presets(void)
{
    hb_dict_t *by_name = hb_dict_init();
    flatten_presets(by_name, hb_presets_builtin_get());
    if (hb_dict_iter_init(by_name) == HB_DICT_ITER_DONE)
    {
        fail("no built-in presets");
    }
    return by_name;
}

/* ---- document --------------------------------------------------------- */

static hb_value_t *schema(const char *handbrake_tag)
{
    hb_dict_t *root = hb_dict_init();
    hb_dict_set_int(root, "schema_format", SCHEMA_FORMAT);
    hb_dict_set_string(root, "handbrake_tag", handbrake_tag);
    hb_dict_set(root, "preset_version", preset_version());
    hb_dict_set(root, "preset_template", preset_template());
    hb_dict_set(root, "template_audio_item", template_audio_item());
    hb_dict_set(root, "video_encoders", video_encoders());
    hb_dict_set(root, "audio_encoders", audio_encoders());
    hb_dict_set(root, "mixdowns", mixdowns());
    hb_dict_set(root, "audio_bitrates", audio_bitrates());
    hb_dict_set(root, "audio_dithers", audio_dithers());
    hb_dict_set(root, "video_framerates", video_framerates());
    hb_dict_set(root, "containers", containers());
    hb_dict_set(root, "filters", filter_schema());
    hb_dict_set(root, "builtin_presets", builtin_presets());
    return root;
}

int main(int argc, char **argv)
{
    if (argc != 2 || argv[1][0] == '\0')
    {
        fail("usage: hb_schema_dump <handbrake-tag>");
    }
    if (hb_global_init_no_hardware() < 0)
    {
        fail("hb_global_init_no_hardware failed");
    }
    hb_value_t *root = schema(argv[1]);
    char *json = hb_value_get_json(root);
    if (json == NULL)
    {
        fail("hb_value_get_json failed");
    }
    printf("%s\n", json);
    free(json);
    hb_value_free(&root);
    return 0;
}
