.PHONY: android catalog web plugins test
android:
	bash scripts/build.sh
catalog:
	python3 scripts/build_catalog.py
web: catalog
	python3 scripts/catalog_server.py
plugins:
	python3 scripts/build_plugins.py
test: catalog
	python3 -m unittest discover -s tests -v
