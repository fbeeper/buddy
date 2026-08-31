#include "BuddyPictureTile.h"

lv_obj_t *BuddyPictureTile_Create(lv_obj_t *tileview)
{
    lv_obj_t *tile = lv_tileview_add_tile(tileview, 0, 0, LV_DIR_BOTTOM);
    LV_IMG_DECLARE(pic);
    lv_obj_t *image = lv_img_create(tile);
    lv_img_set_src(image, &pic);
    lv_obj_align(image, LV_ALIGN_CENTER, 0, 0);
    return tile;
}
