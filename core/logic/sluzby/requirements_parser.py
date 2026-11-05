import os
import re

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
            # 1. Odstránenie fragmentov a parametrov (#..., ?...)
            clean_url = re.sub(r'[#?].*$', '', token).strip()

            # 2. Odstránenie vetvy/tagu na konci (@main, @v1.0.0, @commit)
            if '@' in clean_url and not clean_url.startswith('git@') and not re.match(r'^[a-zA-Z0-9_+\-]+@[a-zA-Z0-9_.\-]+:', clean_url):
                clean_url = clean_url.rsplit('@', 1)[0]
            elif clean_url.startswith('git@') or re.match(r'^[a-zA-Z0-9_+\-]+@[a-zA-Z0-9_.\-]+:', clean_url):
                if ':' in clean_url:
                    prefix, path_part = clean_url.split(':', 1)
                    if '@' in path_part:
                        clean_url = f"{prefix}:{path_part.rsplit('@', 1)[0]}"

            # 3. Získanie posledného segmentu cesty (názov súboru / repozitára)
            norm_path = clean_url.replace('\\', '/').rstrip('/')
            last_segment = norm_path.split('/')[-1] if '/' in norm_path else norm_path

            # 4. Orezanie git prípony .git
            if last_segment.lower().endswith('.git'):
                last_segment = last_segment[:-4]

            # 5. Orezanie archívnych prípon (.tar.gz, .whl, .zip, atď.)
            last_segment = re.sub(r'\.(?:tar\.gz|tar\.bz2|tar\.xz|tgz|whl|zip|egg)$', '', last_segment, flags=re.IGNORECASE)

            # 6. Orezanie čísla verzie na konci súboru (napr. emoji-2.2.0 -> emoji)
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
    def parse(file_path: str, visited_files: set = None, depth: int = 0, base_dir: str = None, pip_e_root: str = None) -> set[str]:
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

        # Nastavenie základného adresára z PÔVODNEJ ne-symlinkovanej cesty
        if base_dir is None:
            try:
                base_dir = os.path.abspath(os.path.dirname(file_path))
            except Exception:
                base_dir = os.path.dirname(abs_path)

        # BEZPEČNOSTNÁ KONTROLA: Path Traversal & Symlink Check pre AKÝKOĽVEK spracovávaný súbor
        try:
            real_base_dir = os.path.normcase(os.path.realpath(base_dir))
            real_target_path = os.path.normcase(abs_path)
            if os.path.commonpath([real_base_dir, real_target_path]) != real_base_dir:
                print(f"[RequirementsParser] Varovanie: Blokovaný pokus o Path Traversal / Symlink mimo povoleného adresára: '{file_path}'")
                return packages
        except ValueError:
            # Nastane na Windows pri prechode na iný disk (napr. C: -> D:) alebo odlišné UNC cesty
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
                
                # Odstránenie komentárov a zlúčenie riadkov rozdelených pomocou '\'
                for raw_line in f:
                    line_str = raw_line.rstrip('\r\n')
                    
                    # 1. Odstránenie in-line komentárov a orezanie
                    line_no_comment = re.sub(r'[\t ]+#.*', '', line_str).strip()
                    
                    # 2. Ignorovanie celoriadkových komentárov a prázdnych riadkov
                    if not line_no_comment or line_no_comment.startswith('#'):
                        continue

                    # 3. Kontrola pokračovacieho znaku '\'
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

                    # Rekurzívne spracovanie '-r' / '--requirement'
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
                                nested_packages = RequirementsParser.parse(nested_abs_path, visited_files, depth + 1, base_dir, pip_e_root)
                                packages.update(nested_packages)
                            except Exception as e:
                                print(f"[RequirementsParser] Varovanie: Zlyhalo spracovanie '{nested_abs_path}': {e}")
                        continue

                    # Spracovanie editable balíčkov (-e / --editable)
                    editable_match = re.match(r'^(?:-e\s+|--editable[\s=]+)(.+)$', line)
                    if editable_match:
                        raw_target = editable_match.group(1).strip().strip('\'"')
                        target_dir = None

                        # Ak to NIE JE git/url odkaz (napr. -e git+https://...)
                        is_vcs = raw_target.startswith(RequirementsParser._URL_SCHEMES) or raw_target.startswith(('git@', 'http://', 'https://'))
                        
                        if not is_vcs:
                            # 1. Kaskáda: Existuje cesta priamo na disku? (plná absolútna cesta napr. F:/.../pip1)
                            norm_raw = os.path.normpath(raw_target)
                            if os.path.isdir(norm_raw):
                                target_dir = norm_raw
                            
                            # 2. Kaskáda: Existuje relatívne voči priečinku projektu / requirements.txt?
                            elif os.path.isdir(os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))):
                                target_dir = os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))

                            # 3. Kaskáda: Existuje priečinok v nastavenom pip_e_root?
                            elif pip_e_root:
                                folder_name = os.path.basename(raw_target.rstrip('/\\'))
                                candidate = os.path.normpath(os.path.join(pip_e_root, folder_name))
                                if os.path.isdir(candidate):
                                    target_dir = candidate

                            # Ak sme našli platný priečinok na disku, načítame skutočné meno zo setup.py / pyproject.toml
                            if target_dir and os.path.isdir(target_dir):
                                pkg_name = RequirementsParser._get_package_name_from_dir(target_dir)
                                if pkg_name:
                                    normalized = RequirementsParser._normalize(pkg_name)
                                    if normalized:
                                        packages.add(normalized)
                                        continue

                            # 4. Záloha (Fallback): Ak priečinok neexistuje, použijeme názov z konca cesty
                            fallback_name = os.path.basename(raw_target.rstrip('/\\'))
                            if fallback_name:
                                clean_cand = RequirementsParser._extract_package_name(fallback_name)
                                if clean_cand:
                                    normalized = RequirementsParser._normalize(clean_cand)
                                    if normalized:
                                        packages.add(normalized)
                                        continue

                        line = raw_target

                    # Ignorovanie ostatných direktív pip inštalátora (-f, -i, --extra-index-url atď.)
                    if line.startswith("-"):
                        continue

                    # Extrakcia a normalizácia balíčka
                    raw_name = RequirementsParser._extract_package_name(line)
                    if raw_name:
                        normalized_name = RequirementsParser._normalize(raw_name)
                        if normalized_name:
                            packages.add(normalized_name)

        except Exception as e:
            print(f"[RequirementsParser] Chyba pri čítaní '{abs_path}': {e}")

        return packages

    # =========================================================================
    # --- NOVÉ METÓDY PRE APT: PLNÉ POŽIADAVKY A OVEROVANIE VERZIÍ ---
    # =========================================================================

    @staticmethod
    def parse_requirements(file_path: str, visited_files: set = None, depth: int = 0, base_dir: str = None, pip_e_root: str = None) -> dict[str, str]:
        """
        Rekurzívne načíta requirements.txt a vráti požiadavky aj s verziami:
        { 'normalizovaný_názov': 'celý_riadok_požiadavky' }
        Príklad výstupu: {'requests': 'requests==2.1', 'pytest': 'pytest>=8.0.0'}
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

                    # 1. Rekurzia cez -r / --requirement
                    req_match = re.match(r'^(?:-r[\s=]+|--requirement[\s=]+|-r(?=[./\\]))(.+)$', line)
                    if req_match:
                        raw_nested_path = req_match.group(1).lstrip("= \t")
                        parts = re.findall(r'(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\S)+', raw_nested_path)
                        nested_rel_path = parts[0].strip('\'"') if parts else ""

                        if nested_rel_path and not nested_rel_path.startswith(RequirementsParser._URL_SCHEMES):
                            current_dir = os.path.dirname(abs_path)
                            nested_abs_path = os.path.realpath(os.path.join(current_dir, nested_rel_path))
                            try:
                                nested = RequirementsParser.parse_requirements(nested_abs_path, visited_files, depth + 1, base_dir, pip_e_root)
                                requirements.update(nested)
                            except Exception:
                                pass
                        continue

                    # 2. Editable balíčky (-e / --editable)
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

                    # 3. Štandardný riadok s balíčkom a verziou
                    raw_name = RequirementsParser._extract_package_name(line)
                    if raw_name:
                        norm_name = RequirementsParser._normalize(raw_name)
                        if norm_name:
                            requirements[norm_name] = line

        except Exception as e:
            print(f"[RequirementsParser] Chyba pri čítaní '{abs_path}': {e}")

        return requirements

    @staticmethod
    def is_satisfied(requirement: str, installed_version: str) -> bool:
        """
        Vyhodnotí, či verzia nainštalovaná na disku spĺňa požiadavku z requirements.txt.
        Čistá logika bez závislosti na externých knižniciach.
        
        Príklad:
            is_satisfied("requests==2.1", "2.0.0") -> False
            is_satisfied("requests==2.1", "2.1.0") -> True
            is_satisfied("requests", "2.0.0")      -> True (nebola zadaná verzia)
        """
        if not installed_version:
            return False

        req_clean = requirement.split(";")[0].strip()

        # URL, git, lokálne cesty a -e balíčky považujeme za splnené, ak už na disku existujú
        if "@" in req_clean or "://" in req_clean or req_clean.startswith((".", "/", "\\", "git+", "-e")):
            return True

        # Odstránenie [extras] napr. requests[socks] -> requests
        req_clean = re.sub(r"\[[^\]]*\]", "", req_clean)

        # Vyhľadanie operátorov a verzií (napr. ==2.1, >=8.0, <9.0)
        operators_found = re.findall(r"([<>=!~]+)\s*([0-9A-Za-z_.\-]+)", req_clean)
        if not operators_found:
            # V requirements nie je žiadne číslo (napr. len "requests") -> akákoľvek verzia stačí
            return True

        def _to_tuple(v_str):
            nums = [int(x) for x in re.findall(r"\d+", v_str)]
            while len(nums) < 4:
                nums.append(0)
            return tuple(nums[:4])

        inst_tuple = _to_tuple(installed_version)

        # Vyhodnotenie všetkých podmienok na riadku
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
    def parse_specs(file_path: str, visited_files: set = None, depth: int = 0, base_dir: str = None, pip_e_root: str = None) -> dict[str, str]:
        """
        Rekurzívne vyparsuje requirements.txt súbor a vráti mapu:
        { normalizovaný_názov: plná_špecifikácia_balíčka (vrátane verzií ==, >=, <= alebo -e ciest) }.

        Podporuje rekurzívne vnorené súbory (-r), editable balíčky (-e),
        odstraňovanie komentárov, spájanie riadkov cez '\\' a bezpečnostné kontroly
        proti cyklom a Path Traversal.

        Args:
            file_path (str): Cesta k requirements.txt súboru.
            visited_files (set, voliteľné): Evidencia navštívených súborov proti zacykleniu.
            depth (int, voliteľné): Aktuálna hĺbka rekurzie.
            base_dir (str, voliteľné): Základný bezpečný adresár.
            pip_e_root (str, voliteľné): Koreňový priečinok lokálnych pip -e balíčkov.

        Returns:
            dict[str, str]: Slovník v tvare {'normalizovaný_názov': 'plná_špecifikácia'}.
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

        # Nastavenie základného adresára z PÔVODNEJ ne-symlinkovanej cesty
        if base_dir is None:
            try:
                base_dir = os.path.abspath(os.path.dirname(file_path))
            except Exception:
                base_dir = os.path.dirname(abs_path)

        # BEZPEČNOSTNÁ KONTROLA: Path Traversal & Symlink Check pre AKÝKOĽVEK spracovávaný súbor
        try:
            real_base_dir = os.path.normcase(os.path.realpath(base_dir))
            real_target_path = os.path.normcase(abs_path)
            if os.path.commonpath([real_base_dir, real_target_path]) != real_base_dir:
                print(f"[RequirementsParser] Varovanie: Blokovaný pokus o Path Traversal / Symlink mimo povoleného adresára: '{file_path}'")
                return specs
        except ValueError:
            # Nastane na Windows pri prechode na iný disk (napr. C: -> D:) alebo odlišné UNC cesty
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
                
                # Odstránenie komentárov a zlúčenie riadkov rozdelených pomocou '\'
                for raw_line in f:
                    line_str = raw_line.rstrip('\r\n')
                    
                    # 1. Odstránenie in-line komentárov a orezanie
                    line_no_comment = re.sub(r'[\t ]+#.*', '', line_str).strip()
                    
                    # 2. Ignorovanie celoriadkových komentárov a prázdnych riadkov
                    if not line_no_comment or line_no_comment.startswith('#'):
                        continue

                    # 3. Kontrola pokračovacieho znaku '\'
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

                    # Rekurzívne spracovanie '-r' / '--requirement'
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
                                nested_specs = RequirementsParser.parse_specs(nested_abs_path, visited_files, depth + 1, base_dir, pip_e_root)
                                specs.update(nested_specs)
                            except Exception as e:
                                print(f"[RequirementsParser] Varovanie: Zlyhalo spracovanie '{nested_abs_path}': {e}")
                        continue

                    # Spracovanie editable balíčkov (-e / --editable)
                    editable_match = re.match(r'^(?:-e\s+|--editable[\s=]+)(.+)$', line)
                    if editable_match:
                        raw_target = editable_match.group(1).strip().strip('\'"')
                        target_dir = None

                        # Ak to NIE JE git/url odkaz (napr. -e git+https://...)
                        is_vcs = raw_target.startswith(RequirementsParser._URL_SCHEMES) or raw_target.startswith(('git@', 'http://', 'https://'))
                        
                        if not is_vcs:
                            # 1. Kaskáda: Existuje cesta priamo na disku? (plná absolútna cesta napr. F:/.../pip1)
                            norm_raw = os.path.normpath(raw_target)
                            if os.path.isdir(norm_raw):
                                target_dir = norm_raw
                            
                            # 2. Kaskáda: Existuje relatívne voči priečinku projektu / requirements.txt?
                            elif os.path.isdir(os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))):
                                target_dir = os.path.normpath(os.path.join(os.path.dirname(abs_path), raw_target))

                            # 3. Kaskáda: Existuje priečinok v nastavenom pip_e_root?
                            elif pip_e_root:
                                folder_name = os.path.basename(raw_target.rstrip('/\\'))
                                candidate = os.path.normpath(os.path.join(pip_e_root, folder_name))
                                if os.path.isdir(candidate):
                                    target_dir = candidate

                            # Ak sme našli platný priečinok na disku, načítame skutočné meno zo setup.py / pyproject.toml
                            if target_dir and os.path.isdir(target_dir):
                                pkg_name = RequirementsParser._get_package_name_from_dir(target_dir)
                                if pkg_name:
                                    normalized = RequirementsParser._normalize(pkg_name)
                                    if normalized:
                                        safe_path = target_dir.replace('\\', '/')
                                        specs[normalized] = f"-e {safe_path}"
                                        continue

                            # 4. Záloha (Fallback): Ak priečinok neexistuje, použijeme názov z konca cesty
                            fallback_name = os.path.basename(raw_target.rstrip('/\\'))
                            if fallback_name:
                                clean_cand = RequirementsParser._extract_package_name(fallback_name)
                                if clean_cand:
                                    normalized = RequirementsParser._normalize(clean_cand)
                                    if normalized:
                                        specs[normalized] = line
                                        continue

                        line = raw_target

                    # Ignorovanie ostatných direktív pip inštalátora (-f, -i, --extra-index-url atď.)
                    if line.startswith("-"):
                        continue

                    # Extrakcia a normalizácia balíčka
                    raw_name = RequirementsParser._extract_package_name(line)
                    if raw_name:
                        normalized_name = RequirementsParser._normalize(raw_name)
                        if normalized_name:
                            specs[normalized_name] = line

        except Exception as e:
            print(f"[RequirementsParser] Chyba pri čítaní '{abs_path}': {e}")

        return specs