#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set

Node = Dict[str, Any]
Link = Dict[str, Any]


# ---------- ID helpers ----------

def svc_id(name: str) -> str:
    return f"svc:{name}"


def bin_id(path_or_name: str) -> str:
    return f"bin:{path_or_name}"


def acg_id(name: str) -> str:
    return f"acg:{name}"


def ep_id(method: str) -> str:
    return f"ep:{method}"


# ---------- Basic helpers ----------

def load_json(path: Path) -> Any | None:
    """Load JSON from a file. Return None on error."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def parse_service_file(path: Path) -> Tuple[List[str], str | None]:
    """
    Parse a .service file to extract service names and Exec= command.
    """
    names: List[str] = []
    exec_cmd: str | None = None

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("Name="):
                value = line.split("=", 1)[1].strip()
                names = [n.strip() for n in value.split(";") if n.strip()]
            elif line.startswith("Exec="):
                exec_cmd = line.split("=", 1)[1].strip()

    return names, exec_cmd


def ensure_node(
    nodes: List[Node],
    node_index: Dict[str, int],
    node_id: str,
    label: str,
    node_type: str,
    **attrs: Any,
) -> int:
    """
    Ensure a node exists; update attributes if already present.
    Returns index in nodes list.
    """
    if node_id in node_index:
        idx = node_index[node_id]
        nodes[idx].update(attrs)
        return idx

    idx = len(nodes)
    node: Node = {
        "id": node_id,
        "label": label,
        "type": node_type,
    }
    node.update(attrs)
    nodes.append(node)
    node_index[node_id] = idx
    return idx


def ensure_service(
    nodes: List[Node],
    node_index: Dict[str, int],
    name: str,
    **attrs: Any,
) -> int:
    return ensure_node(
        nodes,
        node_index,
        node_id=svc_id(name),
        label=name,
        node_type="service",
        **attrs,
    )


def ensure_binary(
    nodes: List[Node],
    node_index: Dict[str, int],
    ident: str,
    **attrs: Any,
) -> int:
    return ensure_node(
        nodes,
        node_index,
        node_id=bin_id(ident),
        label=Path(ident).name,
        node_type="binary",
        binaryPath=ident,
        **attrs,
    )


def ensure_acg(
    nodes: List[Node],
    node_index: Dict[str, int],
    name: str,
    **attrs: Any,
) -> int:
    return ensure_node(
        nodes,
        node_index,
        node_id=acg_id(name),
        label=name,
        node_type="acg",
        **attrs,
    )


def ensure_endpoint(
    nodes: List[Node],
    node_index: Dict[str, int],
    method: str,
    service: str,
    method_path: str,
    **attrs: Any,
) -> int:
    label = method_path or service
    return ensure_node(
        nodes,
        node_index,
        node_id=ep_id(method),
        label=label,
        node_type="endpoint",
        serviceName=service,
        fullMethod=method,
        **attrs,
    )


def add_link(
    links: List[Link],
    source_id: str,
    target_id: str,
    relation: str,
) -> None:
    links.append(
        {
            "source": source_id,
            "target": target_id,
            "relation": relation,
        }
    )


# ---------- Graph construction ----------

def load_services(
    services_dir: Path,
    nodes: List[Node],
    node_index: Dict[str, int],
    links: List[Link],
) -> None:
    if not services_dir.is_dir():
        return

    for svc_file in services_dir.glob("*.service"):
        names, exec_cmd_raw = parse_service_file(svc_file)
        if not names:
            continue

        # Extract binary path from Exec= line (first token)
        exec_binary: str | None = None
        if exec_cmd_raw:
            parts = exec_cmd_raw.split()
            if parts:
                exec_binary = parts[0]

        binary_id: str | None = None
        if exec_binary:
            # This will now merge with roles.d exeName="/usr/sbin/configurator"
            ensure_binary(
                nodes,
                node_index,
                ident=exec_binary,
                execCommand=exec_cmd_raw,        # full Exec= line, including args
                sourceFile=str(svc_file),
            )
            binary_id = bin_id(exec_binary)

        for name in names:
            # Attach binaryPath + full Exec command to service node
            attrs: Dict[str, Any] = {}
            if exec_binary:
                attrs["binaryPath"] = exec_binary
            if exec_cmd_raw:
                attrs["execCommand"] = exec_cmd_raw

            ensure_service(
                nodes,
                node_index,
                name=name,
                **attrs,
            )

            if binary_id:
                add_link(
                    links,
                    source_id=binary_id,
                    target_id=svc_id(name),
                    relation="owns-name",
                )



def load_roles(
    roles_dir: Path,
    nodes: List[Node],
    node_index: Dict[str, int],
    links: List[Link],
) -> None:
    if not roles_dir.is_dir():
        return

    for role_file in roles_dir.glob("*.json"):
        data = load_json(role_file)
        if not isinstance(data, dict):
            continue

        trust_level = data.get("trustLevel")
        rtype = data.get("type")

        allowed_names = data.get("allowedNames") or []
        if not isinstance(allowed_names, list):
            allowed_names = [allowed_names]

        app_id = data.get("appId")
        exe_name = data.get("exeName")
        binary_ident = exe_name or app_id

        binary_id: str | None = None
        if binary_ident:
            ensure_binary(
                nodes,
                node_index,
                ident=binary_ident,
                trustLevel=trust_level,
                roleType=rtype,
                sourceFile=str(role_file),
            )
            binary_id = bin_id(binary_ident)

        # allowedNames -> own bus names
        for svc_name in allowed_names:
            if not isinstance(svc_name, str):
                continue
            ensure_service(
                nodes,
                node_index,
                name=svc_name,
                trustLevel=trust_level,
                roleType=rtype,
            )
            if binary_id:
                add_link(
                    links,
                    source_id=binary_id,
                    target_id=svc_id(svc_name),
                    relation="owns-name",
                )

        # outbound permissions
        permissions = data.get("permissions") or []
        if not isinstance(permissions, list):
            permissions = [permissions]

        for perm in permissions:
            if not isinstance(perm, dict):
                continue

            caller_service = perm.get("service")
            if not caller_service:
                continue

            outbound_raw = perm.get("outbound") or []
            if not isinstance(outbound_raw, list):
                outbound = [outbound_raw]
            else:
                outbound = outbound_raw

            caller_id = svc_id(caller_service)
            caller_attrs: Dict[str, Any] = {}

            if "*" in outbound:
                caller_attrs["outboundAll"] = True

            ensure_service(
                nodes,
                node_index,
                name=caller_service,
                **caller_attrs,
            )

            for target_service in outbound:
                if target_service == "*" or not isinstance(target_service, str):
                    continue

                ensure_service(nodes, node_index, name=target_service)
                add_link(
                    links,
                    source_id=caller_id,
                    target_id=svc_id(target_service),
                    relation="can-call",
                )


def process_api_permissions_file(
    path: Path,
    nodes: List[Node],
    node_index: Dict[str, int],
    links: List[Link],
    processed: Set[Path],
) -> None:
    if path in processed:
        return
    processed.add(path)

    data = load_json(path)
    if not isinstance(data, dict):
        return

    for acg_name, methods in data.items():
        if not isinstance(methods, list):
            continue

        ensure_acg(nodes, node_index, name=acg_name)

        for m in methods:
            method = str(m)
            if "/" in method:
                svc_name, method_path = method.split("/", 1)
            else:
                svc_name = method
                method_path = ""

            ensure_endpoint(
                nodes,
                node_index,
                method=method,
                service=svc_name,
                method_path=method_path,
            )

            add_link(
                links,
                source_id=acg_id(acg_name),
                target_id=ep_id(method),
                relation="acg-method",
            )

            ensure_service(nodes, node_index, name=svc_name)
            add_link(
                links,
                source_id=svc_id(svc_name),
                target_id=ep_id(method),
                relation="provides",
            )


def process_client_permissions_file(
    path: Path,
    nodes: List[Node],
    node_index: Dict[str, int],
    links: List[Link],
    processed: Set[Path],
) -> None:
    if path in processed:
        return
    processed.add(path)

    data = load_json(path)
    if not isinstance(data, dict):
        return

    for target_service, acg_list in data.items():
        if not isinstance(acg_list, list):
            continue

        client_node_id = svc_id(target_service)
        ensure_service(nodes, node_index, name=target_service)

        for acg_name in acg_list:
            if not isinstance(acg_name, str):
                continue

            ensure_acg(nodes, node_index, name=acg_name)
            add_link(
                links,
                source_id=client_node_id,
                target_id=acg_id(acg_name),
                relation="uses-acg",
            )


def process_groups_file(
    path: Path,
    acg_meta: Dict[str, Dict[str, Any]],
    processed: Set[Path],
) -> None:
    if path in processed:
        return
    processed.add(path)

    data = load_json(path)
    if not isinstance(data, dict):
        return

    for key, value in data.items():
        if key == "allowedNames":
            continue

        acg_name = key
        meta = acg_meta.setdefault(
            acg_name,
            {
                "trustLevels": [],
                "public": None,
                "description": None,
            },
        )

        if isinstance(value, list):
            trust_levels = {str(t) for t in value}
            meta["trustLevels"] = sorted(
                set(meta.get("trustLevels", [])) | trust_levels
            )
        elif isinstance(value, dict):
            if "public" in value:
                meta["public"] = bool(value["public"])
            if "description" in value:
                meta["description"] = str(value["description"])


def load_manifests_and_permissions(
    base_dir: Path,
    manifests_dir: Path,
    api_dir: Path,
    client_perm_dir: Path,
    groups_dir: Path,
    nodes: List[Node],
    node_index: Dict[str, int],
    links: List[Link],
    acg_meta: Dict[str, Dict[str, Any]],
) -> None:
    manifest_files: List[Path] = []
    if manifests_dir.is_dir():
        manifest_files.extend(manifests_dir.glob("*.json"))

    processed_api: Set[Path] = set()
    processed_client: Set[Path] = set()
    processed_groups: Set[Path] = set()
    extra_client_perm: Set[Path] = set()

    if client_perm_dir.is_dir():
        extra_client_perm.update(client_perm_dir.glob("*.json"))

    # From manifests
    for mf in manifest_files:
        mdata = load_json(mf)
        if not isinstance(mdata, dict):
            continue

        api_files = mdata.get("apiPermissionFiles") or []
        if not isinstance(api_files, list):
            api_files = [api_files]

        for rel_path in api_files:
            if not isinstance(rel_path, str):
                continue
            path = Path(rel_path)
            if not path.is_absolute():
                path = base_dir / rel_path.lstrip("/")
            if path.exists():
                process_api_permissions_file(
                    path, nodes, node_index, links, processed_api
                )

        client_files = mdata.get("clientPermissionFiles") or []
        if not isinstance(client_files, list):
            client_files = [client_files]

        for rel_path in client_files:
            if not isinstance(rel_path, str):
                continue
            path = Path(rel_path)
            if not path.is_absolute():
                path = base_dir / rel_path.lstrip("/")
            if path.exists():
                process_client_permissions_file(
                    path, nodes, node_index, links, processed_client
                )

        groups_files = mdata.get("groupsFiles") or []
        if not isinstance(groups_files, list):
            groups_files = [groups_files]

        for rel_path in groups_files:
            if not isinstance(rel_path, str):
                continue
            path = Path(rel_path)
            if not path.is_absolute():
                path = base_dir / rel_path.lstrip("/")
            if path.exists():
                process_groups_file(path, acg_meta, processed_groups)

    # api-permissions.d
    if api_dir.is_dir():
        for f in api_dir.glob("*.json"):
            process_api_permissions_file(
                f, nodes, node_index, links, processed_api
            )

    # client-permissions.d
    for f in extra_client_perm:
        process_client_permissions_file(
            f, nodes, node_index, links, processed_client
        )

    # groups.d
    if groups_dir.is_dir():
        for f in groups_dir.glob("*.json"):
            process_groups_file(f, acg_meta, processed_groups)


def build_graph(base_dir: Path) -> Tuple[List[Node], List[Link]]:
    manifests_dir = base_dir / "manifests.d"
    api_dir = base_dir / "api-permissions.d"
    client_perm_dir = base_dir / "client-permissions.d"
    groups_dir = base_dir / "groups.d"
    services_dir = base_dir / "services.d"
    roles_dir = base_dir / "roles.d"

    nodes: List[Node] = []
    links: List[Link] = []
    node_index: Dict[str, int] = {}
    acg_meta: Dict[str, Dict[str, Any]] = {}

    load_services(services_dir, nodes, node_index, links)
    load_roles(roles_dir, nodes, node_index, links)
    load_manifests_and_permissions(
        base_dir,
        manifests_dir,
        api_dir,
        client_perm_dir,
        groups_dir,
        nodes,
        node_index,
        links,
        acg_meta,
    )

    # apply accumulated ACG metadata
    for acg_name, meta in acg_meta.items():
        node_id = acg_id(acg_name)
        idx = node_index.get(node_id)
        if idx is not None:
            nodes[idx].update(meta)

    return nodes, links


# ---------- HTML generation ----------

def generate_html(
    nodes: List[Node],
    links: List[Link],
    output_path: Path,
) -> None:
    here = Path(__file__).resolve().parent
    template_path = here / "template.html"

    if not template_path.is_file():
        print(f"template.html not found next to {__file__}", file=sys.stderr)
        raise SystemExit(1)

    template = template_path.read_text(encoding="utf-8")
    html = template.replace("__NODES__", json.dumps(nodes, indent=2))
    html = html.replace("__LINKS__", json.dumps(links, indent=2))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


# ---------- CLI ----------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate interactive HTML explorer for webOS ACGs / services."
    )
    parser.add_argument(
        "--base-dir",
        default="/usr/share/luna-service2",
        help="Base directory for LS2 security config (default: /usr/share/luna-service2).",
    )
    parser.add_argument(
        "--output",
        default="acg_graph.html",
        help="Output HTML file (default: acg_graph.html).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = Path(args.base_dir)
    output_path = Path(args.output)

    if not base_dir.is_dir():
        print(f"Base directory not found: {base_dir}", file=sys.stderr)
        raise SystemExit(1)

    nodes, links = build_graph(base_dir)
    generate_html(nodes, links, output_path)

    print(f"Wrote {output_path} with {len(nodes)} nodes and {len(links)} links")


if __name__ == "__main__":
    main()
