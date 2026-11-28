import os
import re
from packaging.markers import Marker

class RequirementsParser:
    """
    Samostatná služba na inteligentné čítanie requirements.txt súborov.
    Podporuje rekurzívne vyhľadávanie vnorených súborov (napr. -r base.txt),
    ochranu pred zacyklením a presné parsovanie mien balíčkov (PEP 503 / PEP 508).
    """

    _URL_SCHEMES = ('http://', 'https://', 'git+', 'hg+', 'svn+', 'bzr+', 'file://')

    @staticmethod
    def _normalize(name: str) -> str:
        if not name:
            return ""
            
        name = name.strip()
        if not name:
            return ""
            
        normalized = re.sub(r"[-_.]+", "-", name.lower()).strip('-')
        
        if len(normalized) > 1000:
            return ""
            
        return normalized

    @staticmethod
    def is_marker_valid(requirement_line: str, target_env: dict = None) -> bool:
        """
        Oddelí marker za bodkočiarkou a vyhodnotí ho voči cieľovému prostrediu.
        Vráti True, ak balíček vyhovuje (alebo nemá marker). Vráti False, ak ho treba zahodiť.
        """
        if ";" not in requirement_line:
            return True 
            
        marker_str = requirement_line.split(";", 1)[1].strip()
        try:
            marker = Marker(marker_str)
            if target_env:
                return marker.evaluate(environment=target_env)
            return marker.evaluate() 
        except Exception:
            return True # Ak je marker chybný, pre istotu balík akceptujeme

    @staticmethod
    def _extract_package_name(token: str) -> str | None:
        if not token:
            return None
            
        token = token.strip()
        if not token:
            return None

        # 1. Podpora PEP 508 direct reference syntaxe (napr. "package @ https://..." alebo "package@vendor/pkg.whl")
        if '@' in token and not token.startswith(RequirementsParser._URL_SCHEMES):
            name_part, url_part = token.split('@', 1)
            name_part = name_part.strip()
            url_part = url_part.strip()

            # Ak to NIE JE SSH git adresa (napr. git@github.com:repo.git)
            has_scheme = url_part.startswith(RequirementsParser._URL_SCHEMES) or '://' in url_part
            is_ssh_format = not has_scheme and bool(re.match(r'^[a-zA-Z0-9_+\-]+@[a-zA-Z0-9_.\-]+:', token))

            if not is_ssh_format:
                # Ak časť za @ začína schémou, cestou, obsahuje lomítko alebo je to balíček (.whl, .tar.gz...)
                is_direct_ref_url = (
                    url_part.startswith(RequirementsParser._URL_SCHEMES) or
                    url_part.startswith(('./', '../', '/', '.\\', '..\\')) or
                    re.match(r'^[a-zA-Z]:[/\\]', url_part) or
                    '/' in url_part or '\\' in url_part or
                    url_part.lower().endswith(('.whl', '.tar.gz', '.zip', '.egg'))
                )

                if is_direct_ref_url:
                    match = re.match(r"^([A-Za-z0-9](?:[A-Za-z0-9_.\-]*[A-Za-z0-9])?)", name_part)
                    if match:
                        return match.group(1)

        # 2. Detekcia URL, VCS a SSH adries (napr. git@github.com:user/repo.git#egg=pkg alebo čisté URL/Git)
        is_url_or_path = (
            token.startswith(RequirementsParser._URL_SCHEMES) or 
            token.startswith(('./', '../', '/', '.\\', '..\\')) or
            token.lower().endswith(('.whl', '.tar.gz', '.zip', '.egg')) or ('@' not in token and ('/' in token or '\\' in token)) or
            re.match(r'^[a-zA-Z]:[/\\]', token) or  # Windows abs path (C:\...)
            re.match(r'^[a-zA-Z0-9_+\-]+@[a-zA-Z0-9_.\-]+:', token) # SSH git format (git@host:...)
        )

        if is_url_or_path:
            # A) Priorita 1: Explicitná značka #egg=...
            egg_match = re.search(r'#egg=([^\s&]+)', token)
            if egg_match:
                raw_egg = egg_match.group(1)
                raw_egg = re.sub(r'\[.*?\]', '', raw_egg)
                raw_egg = raw_egg.split('==')[0]
                raw_egg = re.sub(r'-v?\d+(?:\.\d+)+(?:[-._]?[a-zA-Z0-9]+)*$', '', raw_egg)
                match = re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9_.\-]*[A-Za-z0-9])?", raw_egg)
                return match.group(0) if match else None

            # B) Priorita 2 (Fallback heuristika pre čisté URL / Git bez #egg=):
            clean_url = re.sub(r'[#?].*$', '', token).strip()

            if '@' in clean_url and not clean_url.startswith('git@') and not re.match(r'^[a-zA-Z0-9_+\-]+@[a-zA-Z0-9_.\-]+:', clean_url):
                clean_url = clean_url.rsplit('@', 1)[0]
            elif clean_url.startswith('git@') or re.match(r'^[a-zA-Z0-9_+\-]+@[a-zA-Z0-9_.\-]+:', clean_url):
                if ':' in clean_url:
                    prefix, path_part = clean_url.split(':', 1)
                    if '@' in path_part:
                        clean_url = f"{prefix}:{path_part.rsplit('@', 1)[0]}"

            norm_path = clean_url.replace('\\', '/').rstrip('/')
            last_segment = norm_path.split('/')[-1] if '/' in norm_path else norm_path

            if last_segment.lower().endswith('.git'):
                last_segment = last_segment[:-4]

            last_segment = re.sub(r'\.(?:tar\.gz|tar\.bz2|tar\.xz|tgz|whl|zip|egg)$', '', last_segment, flags=re.IGNORECASE)
            last_segment = re.sub(r'-v?\d+(?:\.\d+)+(?:[-._]?[a-zA-Z0-9]+)*$', '', last_segment)

            match = re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9_.\-]*[A-Za-z0-9])?", last_segment)
            return match.group(0) if match else None

        # 3. Štandardný PEP 508 názov balíčka (napr. "requests>=2.25.1", "Flask[async]")
        match = re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9_.\-]*[A-Za-z0-9])?(?=[^A-Za-z0-9_.\-]|$)", token)
        return match.group(0) if match else None
    
    @staticmethod
    def _get_package_name_from_dir(dir_path: str) -> str | None:
        """Načíta názov balíčka z pyproject.toml alebo setup.py v danom adresári."""
        pyproject_path = os.path.join(dir_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            try:
                with open(pyproject_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    match = re.search(r'\[project\][^\[]*?name\s*=\s*["\']([^"\']+)["\']', content, re.DOTALL)
                    if match:
                        return match.group(1)
            except Exception:
                pass

        setup_py_path = os.path.join(dir_path, "setup.py")
        if os.path.isfile(setup_py_path):
            try:
                with open(setup_py_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                    if match:
                        return match.group(1)
            except Exception:
                pass

        return os.path.basename(dir_path)

    @staticmethod
    def parse(file_path: str, visited_files: set = None, depth: int = 0, base_dir: str = None, pip_e_root: str = None, target_env: dict = None) -> set[str]:
        if depth > 50:
            print(f"[RequirementsParser] Varovanie: Prekročená max. hĺbka rekurzie (50) pri '{file_path}'.")
            return set()

        if visited_files is None:
            visited_files = set()

        packages = set()

        try:
            abs_path = os.path.realpath(file_path)
        except Exception:
            return packages

        if base_dir is None:
            try:
                base_dir = os.path.abspath(os.path.dirname(file_path))
            except Exception:
                base_dir = os.path.dirname(abs_path)

        try:
            real_base_dir = os.path.normcase(os.path.realpath(base_dir))
            real_target_path = os.path.normcase(abs_path)
            if os.path.commonpath([real_base_dir, real_target_path]) != real_base_dir:
                print(f"[RequirementsParser] Varovanie: Blokovaný pokus o Path Traversal / Symlink mimo povoleného adresára: '{file_path}'")
                return packages
        except ValueError:
            print(f"[RequirementsParser] Varovanie: Blokovaný prístup na iný disk alebo neplatnú cestu: '{file_path}'")
            return packages

        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            return packages

        if abs_path in visited_files:
            return packages
            
        visited_files.add(abs_path)

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                merged_lines = []
                lines_buffer = []
                
                for raw_line in f:
                    line_str = raw_line.rstrip('\r\n')
                    line_no_comment = re.sub(r'[\t ]+#.*', '', line_str).strip()
                    if not line_no_comment or line_no_comment.startswith('#'):
                        continue

                    num_backslashes = len(line_no_comment) - len(line_no_comment.rstrip('\\'))
                    if num_backslashes % 2 == 1:
                        lines_buffer.append(line_no_comment[:-1])
                    else:
                        lines_buffer.append(line_no_comment)
                        merged_lines.append(''.join(lines_buffer))
                        lines_buffer = []
                        
                if lines_buffer:
                    merged_lines.append(''.join(lines_buffer))

                for line in merged_lines:
                    line = line.strip()

                    req_match = re.match(r'^(?:-r[\s=]+|--requirement[\s=]+|-r(?=[./\\]))(.+)$', line)
                    if req_match:
                        raw_nested_path = req_match.group(1).lstrip("= \t")
                        parts = re.findall(r'(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\S)+', raw_nested_path)
                        nested_rel_path = parts[0].strip('\'"') if parts else ""
                        
                        if nested_rel_path:
                            if nested_rel_path.startswith(RequirementsParser._URL_SCHEMES):
                                print(f"[RequirementsParser] Info: Ignorujem remote URL odkaz '{nested_rel_path}'.")
                                continue

                            current_dir = os.path.dirname(abs_path)
                            nested_abs_path = os.path.realpath(os.path.join(current_dir, nested_rel_path))

                            try:
                                nested_packages = RequirementsParser.parse(nested_abs_path, visited_files, depth + 1, base_dir, pip_e_root, target_env=target_env)
                                packages.update(nested_packages)
                            except Exception as e:
                                print(f"[RequirementsParser] Varovanie: Zlyhalo spracovanie '{nested_abs_path}': {e}")
                        continue

                    # Overenie markeru: Ak neplatí pre cieľové prostredie, riadok zahodíme
                    if not RequirementsParser.is_marker_valid(line, target_env=target_env):
                        continue

                    editable_match = re.match(r'^(?:-e\s+|--editable[\s=]+)(.+)$', line)
                    if editable_match:
                        raw_target = editable_match.group(1).strip().strip('\'"')
                        target_dir = None

                        is_vcs = raw_target.startswith(RequirementsParser._URL_SCHEMES) or raw_target.startswith(('git@', 'http://', 'https://'))
                        
                        if not is_vcs:
                            norm_raw = os.path.normpath(raw_target)
                            if os.path.isdir(norm_raw):
                                target_dir = norm_raw
                            elif os.path.isdir(os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))):
                                target_dir = os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))
                            elif pip_e_root:
                                folder_name = os.path.basename(raw_target.rstrip('/\\'))
                                candidate = os.path.normpath(os.path.join(pip_e_root, folder_name))
                                if os.path.isdir(candidate):
                                    target_dir = candidate

                            if target_dir and os.path.isdir(target_dir):
                                pkg_name = RequirementsParser._get_package_name_from_dir(target_dir)
                                if pkg_name:
                                    normalized = RequirementsParser._normalize(pkg_name)
                                    if normalized:
                                        packages.add(normalized)
                                        continue

                            fallback_name = os.path.basename(raw_target.rstrip('/\\'))
                            if fallback_name:
                                clean_cand = RequirementsParser._extract_package_name(fallback_name)
                                if clean_cand:
                                    normalized = RequirementsParser._normalize(clean_cand)
                                    if normalized:
                                        packages.add(normalized)
                                        continue

                        line = raw_target

                    if line.startswith("-"):
                        continue

                    raw_name = RequirementsParser._extract_package_name(line)
                    if raw_name:
                        normalized_name = RequirementsParser._normalize(raw_name)
                        if normalized_name:
                            packages.add(normalized_name)

        except Exception as e:
            print(f"[RequirementsParser] Chyba pri čítaní '{abs_path}': {e}")

        return packages

    @staticmethod
    def parse_requirements(file_path: str, visited_files: set = None, depth: int = 0, base_dir: str = None, pip_e_root: str = None, target_env: dict = None) -> dict[str, str]:
        """
        Rekurzívne načíta requirements.txt a vráti požiadavky aj s verziami:
        { 'normalizovaný_názov': 'celý_riadok_požiadavky' }
        Ak je zadaný target_env, filtruje riadky okamžite pred pridaním do slovníka (rieši kolízie duplicít).
        """
        if depth > 50:
            return {}

        if visited_files is None:
            visited_files = set()

        requirements = {}

        try:
            abs_path = os.path.realpath(file_path)
        except Exception:
            return requirements

        if base_dir is None:
            try:
                base_dir = os.path.abspath(os.path.dirname(file_path))
            except Exception:
                base_dir = os.path.dirname(abs_path)

        try:
            real_base_dir = os.path.normcase(os.path.realpath(base_dir))
            real_target_path = os.path.normcase(abs_path)
            if os.path.commonpath([real_base_dir, real_target_path]) != real_base_dir:
                return requirements
        except ValueError:
            return requirements

        if not os.path.exists(abs_path) or not os.path.isfile(abs_path) or abs_path in visited_files:
            return requirements

        visited_files.add(abs_path)

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                merged_lines = []
                lines_buffer = []

                for raw_line in f:
                    line_str = raw_line.rstrip('\r\n')
                    line_no_comment = re.sub(r'[\t ]+#.*', '', line_str).strip()
                    if not line_no_comment or line_no_comment.startswith('#'):
                        continue

                    num_backslashes = len(line_no_comment) - len(line_no_comment.rstrip('\\'))
                    if num_backslashes % 2 == 1:
                        lines_buffer.append(line_no_comment[:-1])
                    else:
                        lines_buffer.append(line_no_comment)
                        merged_lines.append(''.join(lines_buffer))
                        lines_buffer = []

                if lines_buffer:
                    merged_lines.append(''.join(lines_buffer))

                for line in merged_lines:
                    line = line.strip()

                    req_match = re.match(r'^(?:-r[\s=]+|--requirement[\s=]+|-r(?=[./\\]))(.+)$', line)
                    if req_match:
                        raw_nested_path = req_match.group(1).lstrip("= \t")
                        parts = re.findall(r'(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\S)+', raw_nested_path)
                        nested_rel_path = parts[0].strip('\'"') if parts else ""

                        if nested_rel_path and not nested_rel_path.startswith(RequirementsParser._URL_SCHEMES):
                            current_dir = os.path.dirname(abs_path)
                            nested_abs_path = os.path.realpath(os.path.join(current_dir, nested_rel_path))
                            try:
                                nested = RequirementsParser.parse_requirements(nested_abs_path, visited_files, depth + 1, base_dir, pip_e_root, target_env=target_env)
                                requirements.update(nested)
                            except Exception:
                                pass
                        continue

                    # KĽÚČOVÝ FILTER: Overenie markeru ešte PRED spracovaním riadku a vložením do slovníka!
                    # Týmto sa predíde prepísaniu kľúča pri dvoch verziách toho istého balíčka.
                    if not RequirementsParser.is_marker_valid(line, target_env=target_env):
                        continue

                    editable_match = re.match(r'^(?:-e\s+|--editable[\s=]+)(.+)$', line)
                    if editable_match:
                        raw_target = editable_match.group(1).strip().strip('\'"')
                        target_dir = None
                        is_vcs = raw_target.startswith(RequirementsParser._URL_SCHEMES) or raw_target.startswith(('git@', 'http://', 'https://'))

                        if not is_vcs:
                            norm_raw = os.path.normpath(raw_target)
                            if os.path.isdir(norm_raw):
                                target_dir = norm_raw
                            elif os.path.isdir(os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))):
                                target_dir = os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))
                            elif pip_e_root:
                                candidate = os.path.normpath(os.path.join(pip_e_root, os.path.basename(raw_target.rstrip('/\\'))))
                                if os.path.isdir(candidate):
                                    target_dir = candidate

                            if target_dir and os.path.isdir(target_dir):
                                pkg_name = RequirementsParser._get_package_name_from_dir(target_dir)
                                if pkg_name:
                                    norm_name = RequirementsParser._normalize(pkg_name)
                                    safe_path = target_dir.replace('\\', '/')
                                    requirements[norm_name] = f"-e {safe_path}"
                                    continue

                        fallback_name = os.path.basename(raw_target.rstrip('/\\'))
                        clean_cand = RequirementsParser._extract_package_name(fallback_name)
                        if clean_cand:
                            norm_name = RequirementsParser._normalize(clean_cand)
                            requirements[norm_name] = line
                        continue

                    if line.startswith("-"):
                        continue

                    raw_name = RequirementsParser._extract_package_name(line)
                    if raw_name:
                        norm_name = RequirementsParser._normalize(raw_name)
                        if norm_name:
                            requirements[norm_name] = line

        except Exception as e:
            print(f"[RequirementsParser] Chyba pri čítaní '{abs_path}': {e}")

        return requirements

    @staticmethod
    def is_satisfied(requirement: str, installed_version: str, target_env: dict = None) -> bool:
        """
        Vyhodnotí, či verzia nainštalovaná na disku spĺňa požiadavku z requirements.txt,
        s rešpektovaním PEP-508 podmienok pre dané prostredie.
        """
        # Ak podmienka neplatí pre tento systém, nepotrebujeme ho (tým pádom je "splnené")
        if not RequirementsParser.is_marker_valid(requirement, target_env):
            return True

        if not installed_version:
            return False

        req_clean = requirement.split(";")[0].strip()

        if "@" in req_clean or "://" in req_clean or req_clean.startswith((".", "/", "\\", "git+", "-e")):
            return True

        req_clean = re.sub(r"\[[^\]]*\]", "", req_clean)

        operators_found = re.findall(r"([<>=!~]+)\s*([0-9A-Za-z_.\-]+)", req_clean)
        if not operators_found:
            return True

        def _to_tuple(v_str):
            nums = [int(x) for x in re.findall(r"\d+", v_str)]
            while len(nums) < 4:
                nums.append(0)
            return tuple(nums[:4])

        inst_tuple = _to_tuple(installed_version)

        for op, target_ver in operators_found:
            target_tuple = _to_tuple(target_ver.rstrip(".*"))

            if op in ("==", "==="):
                if inst_tuple != target_tuple:
                    return False
            elif op == "!=":
                if inst_tuple == target_tuple:
                    return False
            elif op == ">=":
                if inst_tuple < target_tuple:
                    return False
            elif op == "<=":
                if inst_tuple > target_tuple:
                    return False
            elif op == ">":
                if inst_tuple <= target_tuple:
                    return False
            elif op == "<":
                if inst_tuple >= target_tuple:
                    return False
            elif op == "~=":
                if inst_tuple < target_tuple or inst_tuple[0] != target_tuple[0]:
                    return False

        return True

    @staticmethod
    def parse_specs(file_path: str, visited_files: set = None, depth: int = 0, base_dir: str = None, pip_e_root: str = None, target_env: dict = None) -> dict[str, str]:
        """
        Rekurzívne vyparsuje requirements.txt súbor a vráti mapu:
        { normalizovaný_názov: plná_špecifikácia_balíčka }.
        """
        if depth > 50:
            print(f"[RequirementsParser] Varovanie: Prekročená max. hĺbka rekurzie (50) pri '{file_path}'.")
            return {}

        if visited_files is None:
            visited_files = set()

        specs = {}

        try:
            abs_path = os.path.realpath(file_path)
        except Exception:
            return specs

        if base_dir is None:
            try:
                base_dir = os.path.abspath(os.path.dirname(file_path))
            except Exception:
                base_dir = os.path.dirname(abs_path)

        try:
            real_base_dir = os.path.normcase(os.path.realpath(base_dir))
            real_target_path = os.path.normcase(abs_path)
            if os.path.commonpath([real_base_dir, real_target_path]) != real_base_dir:
                print(f"[RequirementsParser] Varovanie: Blokovaný pokus o Path Traversal / Symlink mimo povoleného adresára: '{file_path}'")
                return specs
        except ValueError:
            print(f"[RequirementsParser] Varovanie: Blokovaný prístup na iný disk alebo neplatnú cestu: '{file_path}'")
            return specs

        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            return specs

        if abs_path in visited_files:
            return specs
            
        visited_files.add(abs_path)

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                merged_lines = []
                lines_buffer = []
                
                for raw_line in f:
                    line_str = raw_line.rstrip('\r\n')
                    line_no_comment = re.sub(r'[\t ]+#.*', '', line_str).strip()
                    if not line_no_comment or line_no_comment.startswith('#'):
                        continue

                    num_backslashes = len(line_no_comment) - len(line_no_comment.rstrip('\\'))
                    if num_backslashes % 2 == 1:
                        lines_buffer.append(line_no_comment[:-1])
                    else:
                        lines_buffer.append(line_no_comment)
                        merged_lines.append(''.join(lines_buffer))
                        lines_buffer = []
                        
                if lines_buffer:
                    merged_lines.append(''.join(lines_buffer))

                for line in merged_lines:
                    line = line.strip()

                    req_match = re.match(r'^(?:-r[\s=]+|--requirement[\s=]+|-r(?=[./\\]))(.+)$', line)
                    if req_match:
                        raw_nested_path = req_match.group(1).lstrip("= \t")
                        parts = re.findall(r'(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\S)+', raw_nested_path)
                        nested_rel_path = parts[0].strip('\'"') if parts else ""
                        
                        if nested_rel_path:
                            if nested_rel_path.startswith(RequirementsParser._URL_SCHEMES):
                                print(f"[RequirementsParser] Info: Ignorujem remote URL odkaz '{nested_rel_path}'.")
                                continue

                            current_dir = os.path.dirname(abs_path)
                            nested_abs_path = os.path.realpath(os.path.join(current_dir, nested_rel_path))

                            try:
                                nested_specs = RequirementsParser.parse_specs(nested_abs_path, visited_files, depth + 1, base_dir, pip_e_root, target_env=target_env)
                                specs.update(nested_specs)
                            except Exception as e:
                                print(f"[RequirementsParser] Varovanie: Zlyhalo spracovanie '{nested_abs_path}': {e}")
                        continue

                    # Overenie markeru: Ak neplatí pre cieľové prostredie, riadok zahodíme
                    if not RequirementsParser.is_marker_valid(line, target_env=target_env):
                        continue

                    editable_match = re.match(r'^(?:-e\s+|--editable[\s=]+)(.+)$', line)
                    if editable_match:
                        raw_target = editable_match.group(1).strip().strip('\'"')
                        target_dir = None

                        is_vcs = raw_target.startswith(RequirementsParser._URL_SCHEMES) or raw_target.startswith(('git@', 'http://', 'https://'))
                        
                        if not is_vcs:
                            norm_raw = os.path.normpath(raw_target)
                            if os.path.isdir(norm_raw):
                                target_dir = norm_raw
                            elif os.path.isdir(os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))):
                                target_dir = os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))
                            elif pip_e_root:
                                folder_name = os.path.basename(raw_target.rstrip('/\\'))
                                candidate = os.path.normpath(os.path.join(pip_e_root, folder_name))
                                if os.path.isdir(candidate):
                                    target_dir = candidate

                            if target_dir and os.path.isdir(target_dir):
                                pkg_name = RequirementsParser._get_package_name_from_dir(target_dir)
                                if pkg_name:
                                    normalized = RequirementsParser._normalize(pkg_name)
                                    if normalized:
                                        safe_path = target_dir.replace('\\', '/')
                                        specs[normalized] = f"-e {safe_path}"
                                        continue

                            fallback_name = os.path.basename(raw_target.rstrip('/\\'))
                            if fallback_name:
                                clean_cand = RequirementsParser._extract_package_name(fallback_name)
                                if clean_cand:
                                    normalized = RequirementsParser._normalize(clean_cand)
                                    if normalized:
                                        specs[normalized] = line
                                        continue

                        line = raw_target

                    if line.startswith("-"):
                        continue

                    raw_name = RequirementsParser._extract_package_name(line)
                    if raw_name:
                        normalized_name = RequirementsParser._normalize(raw_name)
                        if normalized_name:
                            specs[normalized_name] = line

        except Exception as e:
            print(f"[RequirementsParser] Chyba pri čítaní '{abs_path}': {e}")

        return specs

    # =========================================================================
    # --- APT ROBUSTNÉ ROZŠÍRENIA ---
    # =========================================================================

    @staticmethod
    def extract_extras(token: str) -> list[str]:
        """Bezpečne vytiahne extras z reťazca (napr. 'requests[socks,ssl]>=2.0' -> ['socks', 'ssl'])."""
        if not token:
            return []
        clean = token.split(';')[0].strip()
        match = re.search(r'\[([^\]]+)\]', clean)
        if match:
            return [RequirementsParser._normalize(e) for e in match.group(1).split(',') if e.strip()]
        return []

    @staticmethod
    def _extract_bracket_list(content: str, keyword: str) -> list[str]:
        """Nájde keyword = [...] a zvládne vnorené hranaté zátvorky ako 'requests[socks]'."""
        match = re.search(rf'{keyword}\s*=\s*\[', content)
        if not match:
            return []
        start = match.end()
        level = 1
        pos = start
        while pos < len(content) and level > 0:
            ch = content[pos]
            if ch == '[':
                level += 1
            elif ch == ']':
                level -= 1
            pos += 1
        if level != 0:
            return []
        block = content[start:pos - 1]
        raw_items = re.findall(r'["\']([^"\']+)["\']', block)
        return [it.strip() for it in raw_items if it.strip()]

    @staticmethod
    def get_project_dependencies(project_path: str) -> list[str]:
        """
        Robustne načíta závislosti lokálneho projektu (pyproject.toml, requirements.txt, setup.cfg, setup.py).
        Nikdy nezlyhá na vnorených [extras] zátvorkách!
        """
        if not project_path or not os.path.isdir(project_path):
            return []

        # 1. Priorita: pyproject.toml (PEP 621)
        pyproject_file = os.path.join(project_path, "pyproject.toml")
        if os.path.isfile(pyproject_file):
            try:
                with open(pyproject_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    deps = RequirementsParser._extract_bracket_list(content, "dependencies")
                    if deps:
                        return deps
            except Exception:
                pass

        # 2. Priorita: requirements.txt v priečinku balíčka (ak existuje)
        inner_req = os.path.join(project_path, "requirements.txt")
        if os.path.isfile(inner_req):
            try:
                reqs_map = RequirementsParser.parse_requirements(inner_req)
                if reqs_map:
                    return list(reqs_map.values())
            except Exception:
                pass

        # 3. Priorita: setup.cfg
        setup_cfg = os.path.join(project_path, "setup.cfg")
        if os.path.isfile(setup_cfg):
            try:
                with open(setup_cfg, "r", encoding="utf-8", errors="replace") as f:
                    in_reqs = False
                    deps = []
                    for line in f:
                        if line.strip().startswith("install_requires"):
                            in_reqs = True
                            continue
                        if in_reqs:
                            if line.startswith((" ", "\t")):
                                val = line.strip()
                                if val:
                                    deps.append(val)
                            else:
                                break
                    if deps:
                        return deps
            except Exception:
                pass

        # 4. Priorita: setup.py
        setup_py = os.path.join(project_path, "setup.py")
        if os.path.isfile(setup_py):
            try:
                with open(setup_py, "r", encoding="utf-8", errors="replace") as f:
                    deps = RequirementsParser._extract_bracket_list(content, "install_requires")
                    if deps:
                        return deps
            except Exception:
                pass

        return []

    @staticmethod
    def parse_extras_map(file_path: str, pip_e_root: str = None, target_env: dict = None) -> dict[str, list[str]]:
        """Vráti mapu {rodič: [extra1, extra2]} využitím existujúceho parsera s voliteľným target_env."""
        extras_map = {}
        if not file_path or not os.path.isfile(file_path):
            return extras_map
        reqs = RequirementsParser.parse_requirements(file_path, pip_e_root=pip_e_root, target_env=target_env)
        for norm_name, full_spec in reqs.items():
            exts = RequirementsParser.extract_extras(full_spec)
            if exts:
                extras_map[norm_name] = exts
        return extras_map