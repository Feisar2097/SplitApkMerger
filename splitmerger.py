from pathlib import Path
from typing import List, Dict, Union
from shutil import move
import re
from sys import argv

from lxml import etree


def get_files(project_folder: Union[str, Path]):
    project_paths = Path(project_folder).expanduser().resolve().glob("*")

    folders = []
    for path in project_paths:
        if path.is_dir(): folders.append(path)

    abis: Dict[str, Dict[str, Union[List, Path]]] = {}
    langs: Dict[str, Dict[str, Union[List[Dict[str, Union[List, Path]]], Path]]] = {}
    drawables: Dict[str, Dict[str, Union[List[Dict[str, Union[List, Path]]], Path]]] = {}
    base: Dict[str, Union[Path, List]] = {}

    for folder in folders:
        abi_dir = [i for i in (folder / "lib").glob("*")]
        if abi_dir:
            abis[abi_dir[0].parts[-1]] = {"targets": [str(i) for i in abi_dir[0].glob("*")],
                                          "destination": folder.parent / "base" / "lib" / abi_dir[0].parts[-1]}

        if folder.parts[-1] == "base":
            base["dir"] = folder
            base["public"] = folder / "res" / "values" / "public.xml"
            base["drawables"] = folder / "res" / "values" / "drawables.xml"
            base["strings"] = folder / "res" / "values" / "strings.xml"
            base["styles"] = folder / "res" / "values" / "styles.xml"
            base["manifest"] = folder / "AndroidManifest.xml"
            base["files"] = [i for i in (folder / "res").rglob("*.xml")]
            continue

        langsp = [i for i in (folder / "res").glob("values-*")]
        for lang_dir in langsp:
            if (lang_dir / "strings.xml").exists() and not str(lang_dir).endswith("dpi"):
                lang = {}
                lang["files"] = [{"targets": [i for i in lang_dir.glob("*")],
                                  "destination": folder.parent / "base" / "res" / lang_dir.parts[-1]}]
                lang["public"] = folder / "res" / "values" / "public.xml"
                langs[str(lang_dir.parts[-1]).replace("values-", "")] = lang

        dpis = [i for i in (folder / "res").glob("drawable-*")]
        if dpis:
            dpis.extend([i for i in (folder / "res").glob("values-*")])
            dpi: Dict[str, any] = {"files": [], "public": folder / "res" / "values" / "public.xml"}

            for dpi_dir in dpis:
                dpi["files"].append({"targets": [i for i in dpi_dir.glob("*")],
                                     "destination": folder.parent / "base" / "res" / dpi_dir.parts[-1]})

            drawables[str(folder.parts[-1]).replace("split_config.", "")] = dpi

    files = {}
    if abis: files["abis"] = abis
    if drawables: files["drawables"] = drawables
    if langs: files["langs"] = langs
    files["base"] = base
    return files if base else None

def process_xmls(target: Path, dest: Path):
    parsed_xml = etree.fromstring(target.read_bytes())

    items = parsed_xml.findall("item")

    for item in items:
        if str(item.attrib["name"]).startswith("APKTOOL_DUMMY"):
            parsed_xml.remove(item)

    if not parsed_xml.getchildren(): return
    dest.mkdir(parents=True, exist_ok=True)
    dest = dest.joinpath(target.name)
    dest.write_bytes(etree.tostring(parsed_xml, encoding="UTF-8"))


def merge_values(base_xmls: Dict[str, Union[Path, List]], split_pubs: List[Path]) -> List[str]:
    splits: Dict[str, Dict[str, str]] = {}
    report: List[str] = []

    for split_pub in split_pubs:
        parsed_xml = etree.fromstring(split_pub.read_bytes())
        items = parsed_xml.getchildren()
        for item in items:
            restype = item.attrib["type"]
            if restype not in splits: splits[restype] = {}
            if not str(item.attrib["name"]).startswith("APKTOOL_DUMMY"):
                splits[restype][item.attrib["id"]] = item.attrib["name"]
    report.append('Merger: Parser: Splitted public.xml parsed')

    public_items = etree.fromstring(base_xmls["public"].read_bytes())
    for item in public_items:
        if str(item.attrib["name"]).startswith("APKTOOL_DUMMY"):
            item.attrib["name"] = splits[item.attrib["type"]][item.attrib["id"]]
    base_xmls["public"].write_bytes(etree.tostring(public_items, encoding="UTF-8", xml_declaration=True))
    report.append('Merger: Public: Base public.xml merged')

    drawables_items = etree.fromstring(base_xmls["drawables"].read_bytes())
    for item in drawables_items:
        if str(item.attrib["name"]).startswith("APKTOOL_DUMMY"):
            item.attrib["name"] = [val for key, val in splits[item.attrib["type"]].items() if str(item.attrib["name"]).split("_")[-1] in key][0]
        elif "APKTOOL_DUMMY" in item.text:
            text: str = item.text
            replace: str = [val for key, val in splits[item.attrib["type"]].items() if text.split("_")[-1] in key][0]
            match: str = text.split("/")[-1]
            item.text = text.replace(match, replace)
    base_xmls["drawables"].write_bytes(etree.tostring(drawables_items, encoding="UTF-8", xml_declaration=True))
    report.append('Merger: Drawables: Base drawables.xml merged')

    styles_items = etree.fromstring(base_xmls["styles"].read_bytes())
    for item in styles_items.iter():
        if "name" in item.attrib and str(item.attrib["name"]).startswith("APKTOOL_DUMMY"):
            item.attrib["name"] = [val for key, val in splits[item.attrib["type"]].items() if str(item.attrib["name"]).split("_")[-1] in key][0]
        elif item.text and "APKTOOL_DUMMY" in item.text:
            text: str = item.text
            restype: str = text.split("/")[0].strip("@")
            replace: str = [val for key, val in splits[restype].items() if text.split("_")[-1] in key][0]
            match: str = text.split("/")[-1]
            item.text = text.replace(match, replace)
    base_xmls["styles"].write_bytes(etree.tostring(styles_items, encoding="UTF-8", xml_declaration=True))
    report.append('Merger: Styles: Base styles.xml merged')

    strings_items = etree.fromstring(base_xmls["strings"].read_bytes())
    for item in strings_items:
        if str(item.attrib["name"]).startswith("APKTOOL_DUMMY"):
            item.attrib["name"] = [val for key, val in splits[item.attrib["type"]].items() if str(item.attrib["name"]).split("_")[-1] in key][0]
    base_xmls["strings"].write_bytes(etree.tostring(strings_items, encoding="UTF-8", xml_declaration=True))
    report.append('Merger: Strings: Base strings.xml merged')

    for xml_file in base_xmls["files"]:
        text = xml_file.read_text()
        results = re.findall(r"\"@drawable/(A.+_([a-f0-9]+))\"", text)
        for result in results:
            replace = [val for key, val in splits["drawable"].items() if result[1] in key][0]
            match = result[0]
            text = text.replace(match, replace)
        xml_file.write_text(text)
        report.append('Merger: Values: Base "{0}" merged'.format(str(xml_file)))
    report.append('Merger: Merging xml complete')

    return report


def patch_manifest(path: Path) -> str:
    manifest = path.read_text()
    path.write_text(manifest.replace('android:extractNativeLibs="false"', "")
                            .replace('android:isSplitRequired="true"', "")
                            .replace('<meta-data android:name="com.android.vending.splits" android:resource="@xml/splits0"/>', "")
                            .replace('<meta-data android:name="com.android.vending.splits.required" android:value="true"/>', ""))
    
    return "Patcher: Manifest patched"


def process_files(splits: Dict[str, Dict]) -> str:
    report: List[str] = []
    publics: List[Path] = []
    for key0, val0 in splits.items():
        if key0 == "abis":
            for key1, val1 in val0.items():
                dest: Path = val1["destination"]
                dest.mkdir(parents=True, exist_ok=True)
                for target in val1["targets"]:
                    move(target, str(dest))
                    report.append('Processor: Abi {0}: Move "{1}" to base folder'.format(key1, target))

        if key0 == "langs" or key0 == "drawables":
            for key1, val1 in val0.items():
                publics.append(val1["public"])
                for dest_dir in val1["files"]:
                    dest: Path = dest_dir["destination"]
                    dest.mkdir(parents=True, exist_ok=True)
                    for target in dest_dir["targets"]:
                        if str(target.name).endswith(".xml"):
                            process_xmls(target, dest)
                            report.append('Processor: Res {0}: Move and clear "{1}" to base folder'.format(key1, target))
                        else:
                            move(str(target), str(dest))
                            report.append('Processor: Res {0}: Move "{1}" to base folder'.format(key1, target))

    report.extend(merge_values(splits["base"], publics))
    report.append(patch_manifest(splits["base"]["manifest"]))

    return "\n".join(report)


if __name__ == "__main__":

    if len(argv) != 2:
        print("Argument error!\nHint: splitmerger.py /path/to/work/dir")
    work_dir = Path(str(argv[1]))
    if work_dir.is_dir() and work_dir.exists():
        print("SplitMerger: Working on " + str(work_dir))
        files = get_files(work_dir)
        for key, splits in files.items():
            print("Founded splits: " + key)
            if key != "base":
                for split in splits.keys():
                    print("\tFounded split: " + split)
        print("SplitMerger: Processing...")
        report = process_files(files)
        print(report, "\nSplitMerger: Splits merged")
    else:
        print("SplitMerger: Path " + str(work_dir) + "is not dir or not exist")