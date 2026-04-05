ADDON_NAME := vertex_color_tool
DIST_DIR := dist
ZIP_PATH := $(DIST_DIR)/$(ADDON_NAME).zip

.PHONY: install uninstall relink zip clean

install:
	./scripts/install_blender_addon.sh install

uninstall:
	./scripts/install_blender_addon.sh uninstall

relink:
	./scripts/install_blender_addon.sh relink

zip: $(ZIP_PATH)

$(ZIP_PATH):
	mkdir -p $(DIST_DIR)
	rm -f $(ZIP_PATH)
	cd . && zip -r $(abspath $(ZIP_PATH)) $(ADDON_NAME)

clean:
	rm -rf $(DIST_DIR)
