pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import Qt.labs.platform 1.0 as Platform

Item {
    id: root
    focus: true

    Keys.onPressed: {
        if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
            event.accepted = true
            root.setAllSelected(true)
        } else if (event.key === Qt.Key_Delete) {
            event.accepted = true
            root.openDelete()
        } else if (event.key === Qt.Key_F5) {
            event.accepted = true
            if (root.currentPath)
                root.goTo(root.currentPath)
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            event.accepted = true
            let items = root.selectedItems()
            if (items.length === 1) {
                if (items[0].isDir)
                    root.goTo(items[0].path)
                else
                    root.openDownload()
            }
        }
    }

    property var backend: null
    property bool busy: false
    property string currentPath: ""
    property var folderTreeModel: []
    property var folderTree: []
    property var itemProperties: ({})
    property int statsFilesInside: -1
    property int statsFoldersInside: -1
    property bool statsLoading: false
    property bool statsExpanded: false
    property bool statsUserCollapsed: false
    property string treeLoadingPath: ""
    property string selectedTreePath: ""
    property bool showHidden: false
    property var allEntries: []
    property string sortBy: "name"
    property string sortOrder: "asc"
    property string theme: "light"
    property int treePanelWidth: 200
    property real dragStartSceneX: 0
    property int dragStartTreeWidth: 260
    property bool isResizing: false

    Component.onCompleted: {
        if (root.backend) {
            root.showHidden = root.backend.showHiddenFiles()
            var savedTheme = root.backend.getTheme()
            if (savedTheme === "light" || savedTheme === "dark")
                root.theme = savedTheme
        }
    }
    property string clipboardOperation: ""
    property int clipboardCount: 0
    property int selectionCount: 0
    property bool extractable: false
    property var folderStats: ({})
    property bool loadingFolder: false
    signal requestNotice(string message)
    signal requestConfirm(string title, string message, var callback)

    readonly property var archiveSuffixes: [
        ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
        ".zip", ".7z", ".rar"
    ]

    // Theme-aware color palette ("system" resolves to light for now).
    readonly property color colorPrimary: theme === "dark" ? "#3b82f6" : "#2563eb"
    readonly property color colorPrimaryHover: theme === "dark" ? "#60a5fa" : "#1d4ed8"
    readonly property color colorPrimaryLight: theme === "dark" ? "#1e3a8a" : "#dbeafe"
    readonly property color colorDanger: theme === "dark" ? "#f87171" : "#dc2626"
    readonly property color colorDangerHover: theme === "dark" ? "#fee2e2" : "#b91c1c"
    readonly property color colorSuccess: theme === "dark" ? "#4ade80" : "#16a34a"
    readonly property color colorWarning: theme === "dark" ? "#fbbf24" : "#f59e0b"
    readonly property color colorSurface: theme === "dark" ? "#0f172a" : "#ffffff"
    readonly property color colorSurfaceHover: theme === "dark" ? "#1e293b" : "#f1f5f9"
    readonly property color colorBorder: theme === "dark" ? "#334155" : "#e2e8f0"
    readonly property color colorTextPrimary: theme === "dark" ? "#f8fafc" : "#0f172a"
    readonly property color colorTextSecondary: theme === "dark" ? "#cbd5e1" : "#475569"
    readonly property color colorTextMuted: theme === "dark" ? "#64748b" : "#94a3b8"
    readonly property color colorBg: theme === "dark" ? "#020617" : "#f8fafc"

    ListModel { id: entryModel }

    Connections {
        target: root.backend

        function onErrorOccurred(message) {
            root.loadingFolder = false
        }

        function onEntriesLoaded(path, entries) {
            root.loadingFolder = false
            root.currentPath = path
            pathField.text = path
            root.allEntries = entries
            root.rebuildModel()
            if (root.backend) root.backend.loadDirectoryStats(path)
        }

        function onClipboardChanged(operation, count) {
            root.clipboardOperation = operation
            root.clipboardCount = count
        }

        function onDirectoryStatsLoaded(path, stats) {
            if (path !== root.currentPath)
                return
            root.folderStats = stats
        }

        function onDirectoryStatsProgress(path, files, folders) {
            if (path !== root.currentPath)
                return
            root.folderStats = { files: files, directories: folders, loading: true }
        }

        function onEntryPropertiesLoaded(path, info) {
            root.itemProperties = info
            statsFilesInside = -1
            statsFoldersInside = -1
            statsLoading = false
            statsExpanded = false
            statsUserCollapsed = false
            propertiesDialog.open()
        }

        function onEntryStatsLoaded(path, stats) {
            statsLoading = false
            if (!statsUserCollapsed) {
                statsExpanded = true
            }
            if (stats.error) {
                root.requestNotice("Failed to load contents stats: " + stats.error)
                statsExpanded = false
                return
            }
            statsFilesInside = stats.files_inside
            statsFoldersInside = stats.folders_inside
        }

        function onEntryStatsProgress(path, files, folders) {
            statsLoading = true
            statsExpanded = true
            statsFilesInside = files
            statsFoldersInside = folders
        }

        function onFileContentLoaded(path, info) {
            if (info.error) {
                root.requestNotice("Failed to read file: " + info.error)
                return
            }
            editorDialog.filePath = path
            editorDialog.isBinary = info.is_binary
            editorDialog.fileSize = info.size
            editorDialog.fileMtime = info.mtime
            editorField.text = info.content
            editorDialog.open()
        }

        function onFileWritten(path, success, message) {
            if (success) {
                root.requestNotice("File saved successfully: " + message)
            } else {
                root.requestNotice("Failed to save file: " + message)
            }
        }

        function onUploadProgress(filename, current, total) {
            uploadDialog.uploading = true
            uploadDialog.progress = total > 0 ? (current / total) : 0
            uploadDialog.progressText = "Uploading " + filename + ": "
                + root.formatSize(current) + " / " + root.formatSize(total)
                + "  (" + Math.round(uploadDialog.progress * 100) + "%)"
        }

        function onDownloadProgress(filename, current, total) {
            downloadDialog.downloading = true
            downloadDialog.progress = total > 0 ? (current / total) : 0
            downloadDialog.progressText = "Downloading " + filename + ": "
                + root.formatSize(current) + " / " + root.formatSize(total)
                + "  (" + Math.round(downloadDialog.progress * 100) + "%)"
        }

        function onUploadCompleted(remotePath, success, message) {
            uploadDialog.uploading = false
            uploadDialog.close()
            if (success) {
                uploadDialog.progress = 1
                uploadDialog.progressText = "Upload completed: " + message
            } else {
                uploadDialog.progress = 0
                uploadDialog.progressText = "Upload failed: " + message
            }
            root.requestNotice(success ? ("Upload completed: " + message) : ("Upload failed: " + message))
        }

        function onDownloadCompleted(localPath, success, message) {
            downloadDialog.downloading = false
            if (success) {
                downloadDialog.progress = 1
                downloadDialog.progressText = "Download completed: " + message
                root.requestNotice("Download completed: " + message)
            } else {
                downloadDialog.progress = 0
                downloadDialog.progressText = "Download failed: " + message
                root.requestNotice("Download failed: " + message)
            }
        }

        function onFolderContentsLoaded(loadedPath, entries) {
            if (loadedPath !== root.treeLoadingPath)
                return
            let node = root.findNodeInTree(root.folderTree, loadedPath)
            if (node) {
                let children = []
                for (let i = 0; i < entries.length; ++i) {
                    let entry = entries[i]
                    if (!entry.is_dir)
                        continue
                    children.push({
                        name: entry.name,
                        path: entry.path,
                        depth: node.depth + 1,
                        children: [],
                        expanded: false,
                        loaded: false,
                        loading: false
                    })
                }
                children.sort(function (a, b) { return a.path.localeCompare(b.path) })
                node.children = children
                node.loaded = true
                node.loading = false
            }
            root.treeLoadingPath = ""
            root.flattenTreeModel()
        }
    }

    function archiveFormatOf(name) {
        let lower = name.toLowerCase()
        for (let i = 0; i < root.archiveSuffixes.length; ++i)
            if (lower.endsWith(root.archiveSuffixes[i]))
                return root.archiveSuffixes[i]
        return ""
    }

    function archiveStem(name) {
        let suffix = archiveFormatOf(name)
        return suffix === "" ? name : name.substring(0, name.length - suffix.length)
    }

    function rebuildModel() {
        entryModel.clear()
        // Sort a copy so the source `allEntries` stays in server order.
        let sorted = root.allEntries.slice()
        sorted.sort(function (a, b) {
            let cmp = 0
            if (root.sortBy === "name") {
                cmp = a.name.localeCompare(b.name)
            } else if (root.sortBy === "size") {
                cmp = (a.size || 0) - (b.size || 0)
            } else if (root.sortBy === "modified") {
                cmp = (a.mtime || 0) - (b.mtime || 0)
            } else if (root.sortBy === "type") {
                // Directories first, then files/links, then by name.
                const aDir = a.is_dir ? 0 : 1
                const bDir = b.is_dir ? 0 : 1
                cmp = aDir - bDir || a.name.localeCompare(b.name)
            }
            return root.sortOrder === "desc" ? -cmp : cmp
        })
        for (let i = 0; i < sorted.length; ++i) {
            let entry = sorted[i]
            if (!root.showHidden && entry.name.startsWith("."))
                continue
            entryModel.append({
                name: entry.name,
                path: entry.path,
                isDir: entry.is_dir,
                isLink: !!entry.is_link,
                size: entry.size,
                mtime: entry.mtime,
                selected: false
            })
        }
        root.refreshSelectionState()
        root.buildFolderTree()
    }

    function ensurePathNodes(path) {
        // Creates (or reuses) placeholder nodes for every ancestor of `path`
        // so the current location is always visible as an expanded spine.
        // Returns the node for `path` itself, or null when path is "/".
        let components = path.split("/").filter(function (c) { return c.length > 0 })
        if (components.length === 0)
            return null
        let parentNodes = root.folderTree
        let node = null
        let parentPath = ""
        for (let i = 0; i < components.length; ++i) {
            parentPath = parentPath === "" ? "/" + components[i] : parentPath + "/" + components[i]
            let existing = root.findNodeInTree(parentNodes, parentPath)
            if (!existing) {
                existing = {
                    name: components[i],
                    path: parentPath,
                    depth: i,
                    children: [],
                    expanded: true,
                    loaded: false,
                    loading: false
                }
                parentNodes.push(existing)
            } else {
                existing.depth = i
                existing.expanded = true
            }
            parentNodes = existing.children
            node = existing
        }
        return node
    }

    function setTopLevelFromEntryModel() {
        // Rebuild the top-level (root "/") folders while preserving expanded
        // state and already-loaded children of nodes we have seen before.
        let existingByPath = {}
        for (let i = 0; i < root.folderTree.length; ++i)
            existingByPath[root.folderTree[i].path] = root.folderTree[i]
        let nodes = []
        for (let i = 0; i < entryModel.count; ++i) {
            let entry = entryModel.get(i)
            if (!entry.isDir)
                continue
            let n = existingByPath[entry.path]
            if (!n) {
                n = {
                    name: entry.name,
                    path: entry.path,
                    depth: 0,
                    children: [],
                    expanded: false,
                    loaded: false,
                    loading: false
                }
            } else {
                n.name = entry.name
                n.depth = 0
                n.loading = false
            }
            nodes.push(n)
        }
        nodes.sort(function (a, b) { return a.path.localeCompare(b.path) })
        root.folderTree = nodes
    }

    function buildFolderTree() {
        if (!root.currentPath)
            return
        root.selectedTreePath = root.currentPath
        if (root.currentPath === "/") {
            root.setTopLevelFromEntryModel()
        } else {
            let node = root.ensurePathNodes(root.currentPath)
            if (node) {
                node.expanded = true
                let children = []
                for (let i = 0; i < entryModel.count; ++i) {
                    let entry = entryModel.get(i)
                    if (!entry.isDir)
                        continue
                    children.push({
                        name: entry.name,
                        path: entry.path,
                        depth: node.depth + 1,
                        children: [],
                        expanded: true,
                        loaded: false,
                        loading: false
                    })
                }
                children.sort(function (a, b) { return a.path.localeCompare(b.path) })
                node.children = children
                node.loaded = true
                node.loading = false
            }
        }
        root.flattenTreeModel()
    }

    function flattenTreeModel() {
        let flat = []
        function recurse(nodes) {
            for (let i = 0; i < nodes.length; ++i) {
                let n = nodes[i]
                flat.push({
                    name: n.name,
                    path: n.path,
                    depth: n.depth,
                    indent: n.depth * 18,
                    expanded: n.expanded,
                    loading: n.loading,
                    isDir: true,
                    selected: n.path === root.selectedTreePath
                })
                if (n.expanded && n.children && n.children.length > 0)
                    recurse(n.children)
            }
        }
        recurse(root.folderTree)
        root.folderTreeModel = flat
    }

    function findNodeInTree(nodes, path) {
        for (let i = 0; i < nodes.length; ++i) {
            let n = nodes[i]
            if (n.path === path)
                return n
            if (n.children && n.children.length > 0) {
                let found = root.findNodeInTree(n.children, path)
                if (found)
                    return found
            }
        }
        return null
    }

    function toggleFolder(nodeData) {
        let node = root.findNodeInTree(root.folderTree, nodeData.path)
        if (!node || node.loading)
            return
        if (node.expanded && node.loaded) {
            // Collapse a fully-loaded folder
            node.expanded = false
        } else {
            // Expand: load children on demand if not yet loaded (no navigation needed)
            node.expanded = true
            if (!node.loaded) {
                node.loading = true
                root.treeLoadingPath = node.path
                root.backend.listFolderContents(node.path)
            }
        }
        root.flattenTreeModel()
    }

    function selectedItems() {
        let items = []
        for (let i = 0; i < entryModel.count; ++i) {
            let item = entryModel.get(i)
            if (item.selected)
                items.push(item)
        }
        return items
    }

    function selectedPaths() {
        return selectedItems().map(function (item) { return item.path })
    }

    function refreshSelectionState() {
        let items = selectedItems()
        root.selectionCount = items.length
        root.extractable = items.length === 1
            && !items[0].isDir
            && root.archiveFormatOf(items[0].name) !== ""
    }

    function directFileCount() {
        let c = 0
        for (let i = 0; i < entryModel.count; ++i)
            if (!entryModel.get(i).isDir) ++c
        return c
    }

    function directFolderCount() {
        let c = 0
        for (let i = 0; i < entryModel.count; ++i)
            if (entryModel.get(i).isDir) ++c
        return c
    }


    function toggleSelection(index, selected) {
        entryModel.setProperty(index, "selected", selected)
        root.refreshSelectionState()
    }

    // Clicking a row selects only that row. Multiple selection is done with
    // the checkboxes or the "Select All" button.
    function selectOnly(index) {
        for (let i = 0; i < entryModel.count; ++i)
            entryModel.setProperty(i, "selected", i === index)
        root.refreshSelectionState()
    }

    function setAllSelected(selected) {
        for (let i = 0; i < entryModel.count; ++i)
            entryModel.setProperty(i, "selected", selected)
        root.refreshSelectionState()
    }

    function goTo(path) {
        if (root.backend === null) {
            root.requestNotice("Connect to the server first.")
            return
        }
        if (!path.startsWith("/")) {
            root.requestNotice("Enter an absolute Linux folder path (starting with /).")
            return
        }
        root.loadingFolder = true
        root.backend.navigate(path)
    }

    function goUp() {
        if (root.currentPath === "" || root.currentPath === "/")
            return
        let parts = root.currentPath.split("/").filter(function (part) {
            return part.length > 0
        })
        parts.pop()
        root.goTo("/" + parts.join("/"))
    }

    function formatSize(bytes) {
        if (bytes < 1024)
            return bytes + " B"
        if (bytes < 1024 * 1024)
            return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024)
            return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB"
    }

    function formatTime(seconds) {
        if (!seconds)
            return "—"
        return Qt.formatDateTime(new Date(seconds * 1000), "yyyy-MM-dd HH:mm")
    }

    // Convert a file:// URL to a local filesystem path
    function localPathFromUrl(url) {
        let s = url.toString()
        if (s.startsWith("file:///")) s = s.substring(8)
        else if (s.startsWith("file://")) s = s.substring(7)
        return decodeURIComponent(s)
    }

    // Extract filename from a local path (handles both / and \ separators)
    function fileNameFromPath(path) {
        let parts = path.split(/[\\/]/)
        return parts[parts.length - 1]
    }

    function requireBackend() {
        if (root.backend === null) {
            root.requestNotice("Connect to the server first.")
            return false
        }
        return true
    }

    function requireSelection() {
        if (root.selectionCount === 0) {
            root.requestNotice("Select at least one item first.")
            return false
        }
        return true
    }

    function startCopy() {
        if (requireBackend() && requireSelection())
            root.backend.copySelection(root.selectedPaths())
    }

    function startCut() {
        if (requireBackend() && requireSelection())
            root.backend.cutSelection(root.selectedPaths())
    }

    function pasteHere() {
        if (!requireBackend())
            return
        if (root.clipboardCount === 0) {
            root.requestNotice("The clipboard is empty. Copy or cut items first.")
            return
        }
        root.backend.pasteInto(root.currentPath)
    }

    function openRename() {
        let items = selectedItems()
        if (items.length !== 1) {
            root.requestNotice("Select exactly one item to rename.")
            return
        }
        renameDialog.originalPath = items[0].path
        renameField.text = items[0].name
        renameDialog.open()
    }

    function openDelete() {
        if (!requireSelection())
            return
        let items = selectedItems()
        let lines = []
        for (let i = 0; i < items.length && i < 8; ++i)
            lines.push("• " + items[i].name)
        if (items.length > 8)
            lines.push("… and " + (items.length - 8) + " more")
        root.requestConfirm(
            "Confirm Deletion",
            "Permanently delete " + items.length
            + " item(s) from the server?\n\n" + lines.join("\n")
            + "\n\nThis cannot be undone.",
            function() { root.backend.deleteSelection(root.selectedPaths()) }
        )
    }

    function openCompress() {
        if (!requireSelection())
            return
        compressNameField.text = "archive"
        compressFormatBox.currentIndex = 0
        compressDialog.open()
    }

    function openExtract() {
        let items = selectedItems()
        if (items.length !== 1) {
            root.requestNotice("Select exactly one archive file to extract.")
            return
        }
        if (items[0].isDir || root.archiveFormatOf(items[0].name) === "") {
            root.requestNotice(
                "Only .tar.gz, .tar.bz2, .tar.xz, .zip, .7z and .rar archives can be extracted."
            )
            return
        }
        extractDialog.archivePath = items[0].path
        extractField.text = root.archiveStem(items[0].name)
        extractDialog.open()
    }

    function openItemProperties() {
        if (!requireBackend())
            return
        let items = selectedItems()
        if (items.length !== 1) {
            root.requestNotice("Select exactly one item to view its properties.")
            return
        }
        root.backend.loadEntryProperties(items[0].path)
    }

    function openEditor() {
        if (!requireBackend())
            return
        let items = selectedItems()
        if (items.length !== 1) {
            root.requestNotice("Select exactly one file to edit.")
            return
        }
        if (items[0].isDir) {
            root.requestNotice("Cannot edit a folder. Select a file.")
            return
        }
        root.backend.readFileContent(items[0].path)
    }

    function openUpload() {
        if (!requireBackend() || root.currentPath === "") {
            root.requestNotice("Connect to the server and navigate to a folder first.")
            return
        }
        uploadDialog.remotePath = root.currentPath
        uploadDialog.resetUpload()
        uploadFileDialog.open()
    }

    function openDownload() {
        if (!requireBackend())
            return
        let items = selectedItems()
        if (items.length !== 1) {
            root.requestNotice("Select exactly one file to download.")
            return
        }
        if (items[0].isDir) {
            root.requestNotice("Cannot download a folder. Select a file.")
            return
        }
        downloadDialog.remotePath = items[0].path
        downloadDialog.remoteFileName = items[0].name
        downloadDialog.resetDownload()
        downloadDialog.open()
    }

    function propertyRows() {
        let info = root.itemProperties || {}
        let rows = []
        function add(key, value) {
            rows.push({ key: key, value: String(value) })
        }
        if (info.error) {
            add("Error", info.error)
            return rows
        }
        add("Name", info.name || "—")
        add("Full path", info.path || "—")
        add("Type", info.kind || "—")
        if (info.kind === "Symbolic link") {
            add("Link target", info.target || "—")
            add("Resolves to", info.resolved || "—")
        }
        if (info.kind !== "Folder")
            add("Size", root.formatSize(info.size || 0) + " (" + (info.size || 0) + " bytes)")
        add("Permissions", (info.mode || "—") + "  (" + (info.octal_mode || "—") + ")")
        add("Owner", (info.owner || "—") + "  (uid " + (info.uid !== undefined ? info.uid : "—") + ")")
        add("Group", (info.group || "—") + "  (gid " + (info.gid !== undefined ? info.gid : "—") + ")")
        add("Hard links", info.links !== undefined ? info.links : "—")
        add("Modified", root.formatTime(info.mtime))
        add("Accessed", root.formatTime(info.atime))
        add("Changed", root.formatTime(info.ctime))
        add("Inode number", info.inode !== undefined ? info.inode : "—")
        if (info.kind === "Folder" && statsFilesInside >= 0 && statsExpanded) {
            add("Files inside", statsFilesInside)
            add("Folders inside", statsFoldersInside)
            add("Items inside", statsFilesInside + statsFoldersInside)
        }
        return rows
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Left: Folder Tree Panel
        Rectangle {
            Layout.preferredWidth: root.treePanelWidth
            Layout.minimumWidth: 200
            Layout.maximumWidth: 800
            Layout.fillHeight: true
            color: root.colorSurface
            border.color: root.colorBorder
            border.width: 1

            // Resize handle on right edge of tree panel
            Rectangle {
                width: 6
                height: parent.height
                anchors.right: parent.right
                color: "transparent"

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.SizeHorCursor
                    onPressed: (mouse) => {
                        root.isResizing = true
                        root.dragStartSceneX = parent.mapToItem(null, mouse.x, mouse.y).x
                        root.dragStartTreeWidth = root.treePanelWidth
                    }
                    onReleased: () => {
                        root.isResizing = false
                    }
                    onPositionChanged: (mouse) => {
                        if (!root.isResizing)
                            return
                        var sceneX = parent.mapToItem(null, mouse.x, mouse.y).x
                        var newWidth = root.dragStartTreeWidth + (sceneX - root.dragStartSceneX)
                        if (newWidth < 200)
                            newWidth = 200
                        if (newWidth > 800)
                            newWidth = 800
                        root.treePanelWidth = newWidth
                    }
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 6

                Label {
                    text: "Folders"
                    font.bold: true
                    color: root.colorTextPrimary
                    font.pixelSize: 13
                    Layout.fillWidth: true
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: root.colorBorder
                }

                ListView {
                    id: folderTreeView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: root.folderTreeModel
                    spacing: 2
                    ScrollBar.vertical: ScrollBar {}

                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        height: 32
                        color: root.colorSurfaceHover
                        radius: 4

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: 4

                            Item {
                                width: modelData.indent
                                height: 1
                            }

                            Item {
                                width: 18
                                height: 18
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: !modelData.loading
                                    onClicked: root.toggleFolder(modelData)
                                }
                                Label {
                                    anchors.centerIn: parent
                                    text: modelData.loading
                                        ? "⟳"
                                        : (modelData.expanded ? "▼" : "▶")
                                    font.pixelSize: 11
                                    color: modelData.loading
                                        ? root.colorWarning
                                        : root.colorTextMuted
                                }
                            }

                            Label {
                                text: modelData.name
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                color: modelData.selected ? root.colorPrimary : root.colorTextPrimary
                                font.bold: modelData.selected
                                font.pixelSize: 12
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: root.goTo(modelData.path)
                                }
                            }
                        }
                    }
                }
            }
        }

        // Right: File Explorer content
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

        // Path Bar
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            height: 44

            Button {
                id: upBtn
                text: "↑ Up"
                enabled: !root.busy && root.currentPath !== "" && root.currentPath !== "/"
                onClicked: root.goUp()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            TextField {
                id: pathField
                placeholderText: "/data/deepzoom"
                Layout.fillWidth: true
                height: 36
                font.pixelSize: 13
                padding: 8
                onAccepted: root.goTo(pathField.text)
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Go"
                enabled: !root.busy
                onClicked: root.goTo(pathField.text)
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Refresh"
                enabled: !root.busy && root.currentPath !== ""
                onClicked: root.backend.refresh()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            CheckBox {
                text: "Show hidden"
                checked: root.showHidden
                font.pixelSize: 12
                onToggled: {
                    root.showHidden = checked
                    root.rebuildModel()
                    if (root.backend) {
                        root.backend.setShowHiddenFiles(checked)
                    }
                }
            }
        }

        // Action Toolbar
        Flow {
            Layout.fillWidth: true
            spacing: 8

            // Primary actions
            Button {
                text: "New Folder"
                enabled: !root.busy && root.currentPath !== ""
                onClicked: { newFolderField.text = ""; newFolderDialog.open() }
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Rename"
                enabled: !root.busy && root.selectionCount === 1
                onClicked: root.openRename()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Properties"
                enabled: !root.busy && root.selectionCount === 1
                onClicked: root.openItemProperties()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Item { width: 8; height: 1 }

            // Clipboard actions
            Button {
                text: "Cut"
                enabled: !root.busy && root.selectionCount > 0
                onClicked: root.startCut()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Copy"
                enabled: !root.busy && root.selectionCount > 0
                onClicked: root.startCopy()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Paste"
                enabled: !root.busy && root.clipboardCount > 0 && root.currentPath !== ""
                onClicked: root.pasteHere()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.clipboardCount > 0 ? root.colorPrimaryLight : root.colorSurface
                    border.color: root.clipboardCount > 0 ? root.colorPrimary : root.colorBorder
                    border.width: 1
                }
            }
            Item { width: 8; height: 1 }

            // Dangerous actions
            Button {
                text: "Delete"
                enabled: !root.busy && root.selectionCount > 0
                onClicked: root.openDelete()
                height: 36
                font.pixelSize: 12
                font.bold: true
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorDanger
                    border.color: root.colorDanger
                    border.width: 1
                }
                contentItem: Text {
                    text: "Delete"
                    color: "#ffffff"
                    font.pixelSize: 12
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
            Item { width: 8; height: 1 }

            // File editor action
            Button {
                text: "Edit"
                enabled: !root.busy && root.selectionCount === 1 && !selectedItems()[0]?.isDir
                onClicked: root.openEditor()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }

            // Upload/Download actions
            Button {
                text: "Upload"
                enabled: !root.busy && root.currentPath !== ""
                onClicked: root.openUpload()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Download"
                enabled: !root.busy && root.selectionCount === 1 && !selectedItems()[0]?.isDir
                onClicked: root.openDownload()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Item { width: 8; height: 1 }

            Button {
                text: "Compress"
                enabled: !root.busy && root.selectionCount > 0
                onClicked: root.openCompress()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Extract"
                enabled: !root.busy && root.extractable
                onClicked: root.openExtract()
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Item { width: 12; height: 1 }
            Button {
                text: "Select All"
                enabled: !root.busy && entryModel.count > 0
                onClicked: root.setAllSelected(true)
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Select None"
                enabled: !root.busy && entryModel.count > 0
                onClicked: root.setAllSelected(false)
                height: 36
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
        }

        // File List
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.colorSurface
            border.color: root.colorBorder
            border.width: 1
            radius: 8

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 4
                spacing: 2

                // Header Row - mirrors the row delegate layout (margins, spacing, widths)
                // so the column labels line up exactly with the files/folders below.
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 8
                    Layout.rightMargin: 8
                    spacing: 8
                    height: 36

                    // Checkbox column spacer (width matches the row checkboxes)
                    Item { Layout.preferredWidth: 20 }

                    // Name column
                    Item {
                        Layout.fillWidth: true
                        Rectangle {
                            anchors.fill: parent
                            color: nameHover.containsMouse ? root.colorSurfaceHover : "transparent"
                            radius: 4
                        }
                        MouseArea {
                            id: nameHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (root.sortBy === "name")
                                    root.sortOrder = root.sortOrder === "asc" ? "desc" : "asc"
                                else {
                                    root.sortBy = "name"
                                    root.sortOrder = "asc"
                                }
                                root.rebuildModel()
                            }
                        }
                        RowLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            Label {
                                text: "Name"
                                font.bold: true
                                color: root.colorTextPrimary
                                font.pixelSize: 11
                            }
                            Label {
                                text: root.sortBy === "name" ? (root.sortOrder === "asc" ? "▲" : "▼") : ""
                                color: root.colorPrimary
                                font.pixelSize: 9
                            }
                        }
                    }

                    // Size column
                    Item {
                        Layout.preferredWidth: 90
                        Rectangle {
                            anchors.fill: parent
                            color: sizeHover.containsMouse ? root.colorSurfaceHover : "transparent"
                            radius: 4
                        }
                        MouseArea {
                            id: sizeHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (root.sortBy === "size")
                                    root.sortOrder = root.sortOrder === "asc" ? "desc" : "asc"
                                else {
                                    root.sortBy = "size"
                                    root.sortOrder = "asc"
                                }
                                root.rebuildModel()
                            }
                        }
                        RowLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            Label {
                                text: "Size"
                                font.bold: true
                                color: root.colorTextPrimary
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignRight
                            }
                            Label {
                                text: root.sortBy === "size" ? (root.sortOrder === "asc" ? "▲" : "▼") : ""
                                color: root.colorPrimary
                                font.pixelSize: 9
                            }
                        }
                    }

                    // Modified column
                    Item {
                        Layout.preferredWidth: 140
                        Rectangle {
                            anchors.fill: parent
                            color: modifiedHover.containsMouse ? root.colorSurfaceHover : "transparent"
                            radius: 4
                        }
                        MouseArea {
                            id: modifiedHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (root.sortBy === "modified")
                                    root.sortOrder = root.sortOrder === "asc" ? "desc" : "asc"
                                else {
                                    root.sortBy = "modified"
                                    root.sortOrder = "asc"
                                }
                                root.rebuildModel()
                            }
                        }
                        RowLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            Label {
                                text: "Modified"
                                font.bold: true
                                color: root.colorTextPrimary
                                font.pixelSize: 11
                            }
                            Label {
                                text: root.sortBy === "modified" ? (root.sortOrder === "asc" ? "▲" : "▼") : ""
                                color: root.colorPrimary
                                font.pixelSize: 9
                            }
                        }
                    }

                    // Type column
                    Item {
                        Layout.preferredWidth: 70
                        Rectangle {
                            anchors.fill: parent
                            color: typeHover.containsMouse ? root.colorSurfaceHover : "transparent"
                            radius: 4
                        }
                        MouseArea {
                            id: typeHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                if (root.sortBy === "type")
                                    root.sortOrder = root.sortOrder === "asc" ? "desc" : "asc"
                                else {
                                    root.sortBy = "type"
                                    root.sortOrder = "asc"
                                }
                                root.rebuildModel()
                            }
                        }
                        RowLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            Label {
                                text: "Type"
                                font.bold: true
                                color: root.colorTextPrimary
                                font.pixelSize: 11
                            }
                            Label {
                                text: root.sortBy === "type" ? (root.sortOrder === "asc" ? "▲" : "▼") : ""
                                color: root.colorPrimary
                                font.pixelSize: 9
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: root.colorBorder
                }

                // File List View
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: fileList
                        anchors.fill: parent
                        clip: true
                        model: entryModel
                        spacing: 1
                        ScrollBar.vertical: ScrollBar {}

                        delegate: Rectangle {
                            id: row
                            required property int index
                            required property string name
                            required property string path
                            required property bool isDir
                            required property bool isLink
                            required property real size
                            required property real mtime
                            required property bool selected

                            width: ListView.view.width
                            height: 40
                            radius: 4
                            color: selected
                                ? root.colorPrimaryLight
                                : (rowMouse.containsMouse ? root.colorSurfaceHover : "transparent")

                            MouseArea {
                                id: rowMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton
                                // Clicking a row selects only that row.
                                onClicked: root.selectOnly(row.index)
                                onDoubleClicked: {
                                    if (row.isDir && !root.busy)
                                        root.goTo(row.path)
                                }
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8

                                CheckBox {
                                    id: rowCheckBox
                                    checked: row.selected
                                    enabled: !root.busy
                                    // The checkbox is the multi-select control:
                                    // toggling it never clears the other rows.
                                    onToggled: {
                                        root.toggleSelection(row.index, checked)
                                        // Restore the binding, the user interaction
                                        // would otherwise break it permanently.
                                        rowCheckBox.checked = Qt.binding(function () {
                                            return row.selected
                                        })
                                    }
                                }

                                Label {
                                    text: row.name
                                    Layout.fillWidth: true
                                    elide: Text.ElideMiddle
                                    color: row.isDir ? root.colorPrimary : root.colorTextPrimary
                                    font.bold: row.isDir
                                    font.pixelSize: 13
                                }
                                Label {
                                    text: row.isDir ? "—" : root.formatSize(row.size)
                                    color: root.colorTextSecondary
                                    Layout.preferredWidth: 90
                                    horizontalAlignment: Text.AlignRight
                                    font.pixelSize: 12
                                }
                                Label {
                                    text: root.formatTime(row.mtime)
                                    color: root.colorTextSecondary
                                    Layout.preferredWidth: 140
                                    font.pixelSize: 12
                                }
                                Label {
                                    text: row.isDir ? "Folder" : (row.isLink ? "Link" : "File")
                                    color: root.colorTextSecondary
                                    Layout.preferredWidth: 70
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: entryModel.count === 0 && !root.loadingFolder
                        text: root.currentPath === ""
                            ? "Connect to the server to explore files."
                            : (root.loadingFolder ? "Loading…" : "This folder is empty.")
                        color: root.colorTextMuted
                        font.pixelSize: 13
                    }

                    // Loading overlay - shown while a folder is being read.
                    // It disappears automatically once the entries arrive.
                    Rectangle {
                        id: loadingOverlay
                        anchors.fill: parent
                        visible: root.loadingFolder
                        color: root.colorSurface
                        z: 10

                        Column {
                            anchors.centerIn: parent
                            spacing: 12

                            BusyIndicator {
                                width: 48
                                height: 48
                                running: root.loadingFolder
                            }

                            Label {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: root.currentPath ? ("Loading " + root.currentPath + "…") : "Loading folder…"
                                color: root.colorTextPrimary
                                font.pixelSize: 13
                            }
                        }
                    }
                }
            }
        }

        // Status Bar
        RowLayout {
            Layout.fillWidth: true
            height: 32
            Label {
                text: root.selectionCount + " of " + entryModel.count + " selected"
                color: root.colorTextSecondary
                font.pixelSize: 11
                Layout.leftMargin: 12
                Layout.alignment: Qt.AlignVCenter
            }
            Item { Layout.fillWidth: true }
            Label {
                text: "Files: " + root.directFileCount()
                    + "  |  Folders: " + root.directFolderCount()
                color: root.colorTextSecondary
                font.pixelSize: 11
                Layout.alignment: Qt.AlignVCenter
            }
            Label {
                text: root.clipboardCount > 0
                    ? "Clipboard: " + root.clipboardCount + " item(s) — "
                        + (root.clipboardOperation === "cut" ? "move" : "copy")
                    : "Clipboard empty"
                color: root.clipboardCount > 0 ? root.colorPrimary : root.colorTextMuted
                font.pixelSize: 11
                font.weight: root.clipboardCount > 0 ? Font.Medium : Font.Normal
                Layout.rightMargin: 12
                Layout.alignment: Qt.AlignVCenter
            }
        }
        }
    }

    // --- Dialogs ---

    // Compress Dialog
    Dialog {
        id: compressDialog
        title: "Create Archive"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 440

        onAccepted: root.backend.compressSelection(
            root.selectedPaths(),
            compressNameField.text,
            compressFormatBox.currentText
        )

        contentItem: Column {
            width: 400
            spacing: 12
            anchors.margins: 16

            Label { text: "Archive name"; font.pixelSize: 12; color: root.colorTextSecondary }
            TextField {
                id: compressNameField
                width: parent.width
                height: 36
                placeholderText: "archive"
                font.pixelSize: 13
                padding: 8
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Label { text: "Format"; font.pixelSize: 12; color: root.colorTextSecondary }
            ComboBox {
                id: compressFormatBox
                width: parent.width
                height: 36
                model: ["tar.gz", "tar.bz2", "tar.xz", "zip", "7z", "rar"]
                font.pixelSize: 13
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.colorTextMuted
                font.pixelSize: 11
                text: "Compresses " + root.selectionCount
                    + " selected item(s) from " + root.currentPath
                    + " into a new archive in the same folder."
            }
        }
    }

    // Extract Dialog
    Dialog {
        id: extractDialog
        property string archivePath: ""
        title: "Extract Archive"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 440

        onAccepted: root.backend.extractArchive(
            extractDialog.archivePath,
            extractField.text
        )

        contentItem: Column {
            width: 400
            spacing: 12
            anchors.margins: 16

            Label { text: "Destination folder"; font.pixelSize: 12; color: root.colorTextSecondary }
            TextField {
                id: extractField
                width: parent.width
                height: 36
                placeholderText: "Folder name or absolute path"
                font.pixelSize: 13
                padding: 8
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Label {
                width: parent.width
                wrapMode: Text.WrapAnywhere
                color: root.colorTextMuted
                font.pixelSize: 11
                text: "A relative name is created next to the archive. "
                    + "The archive will be extracted and opened."
            }
        }
    }

    // Rename Dialog
    Dialog {
        id: renameDialog
        property string originalPath: ""
        title: "Rename Item"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 440

        onAccepted: root.backend.renameEntry(renameDialog.originalPath, renameField.text)

        contentItem: Column {
            width: 400
            spacing: 12
            anchors.margins: 16

            Label { text: "New name"; font.pixelSize: 12; color: root.colorTextSecondary }
            TextField {
                id: renameField
                width: parent.width
                height: 36
                font.pixelSize: 13
                padding: 8
                onAccepted: renameDialog.accept()
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
        }
    }

    // New Folder Dialog
    Dialog {
        id: newFolderDialog
        title: "New Folder"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 440

        onAccepted: root.backend.createDirectory(root.currentPath, newFolderField.text)

        contentItem: Column {
            width: 400
            spacing: 12
            anchors.margins: 16

            Label { text: "Folder name"; font.pixelSize: 12; color: root.colorTextSecondary }
            TextField {
                id: newFolderField
                width: parent.width
                height: 36
                placeholderText: "New folder"
                font.pixelSize: 13
                padding: 8
                onAccepted: newFolderDialog.accept()
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
        }
    }

    // Properties Dialog
    Dialog {
        id: propertiesDialog
        title: "Properties"
        modal: true
        standardButtons: Dialog.Ok
        anchors.centerIn: parent
        width: 560

        contentItem: Column {
            width: 520
            spacing: 2
            anchors.margins: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    text: statsExpanded ? "Show less" : "Show more"
                    enabled: !statsLoading && root.itemProperties.kind === "Folder"
                    onClicked: {
                        if (statsFilesInside < 0) {
                            statsLoading = true
                            statsExpanded = true
                            statsUserCollapsed = false
                            statsFilesInside = 0
                            statsFoldersInside = 0
                            root.backend.loadEntryStats(root.itemProperties.path)
                        } else {
                            statsExpanded = !statsExpanded
                            statsUserCollapsed = !statsExpanded
                        }
                    }
                    height: 32
                    font.pixelSize: 11
                    background: Rectangle {
                        implicitHeight: 32
                        radius: 6
                        color: statsExpanded ? root.colorPrimaryLight : root.colorSurface
                        border.color: statsExpanded ? root.colorPrimary : root.colorBorder
                        border.width: 1
                    }
                }

                Label {
                    text: statsLoading ? "Counting contents…" : ""
                    color: root.colorTextMuted
                    font.pixelSize: 11
                }

                Item { Layout.fillWidth: true }
            }

            Repeater {
                model: root.propertyRows()

                RowLayout {
                    required property var modelData
                    width: parent.width
                    spacing: 12
                    height: 28

                    Label {
                        text: modelData.key
                        color: root.colorTextSecondary
                        Layout.preferredWidth: 120
                        font.pixelSize: 12
                    }
                    Label {
                        text: modelData.value
                        color: root.colorTextPrimary
                        wrapMode: Text.WrapAnywhere
                        Layout.fillWidth: true
                        font.pixelSize: 12
                    }
                }
            }
        }
    }

    // File Editor Dialog
    Dialog {
        id: editorDialog
        property string filePath: ""
        property bool isBinary: false
        property int fileSize: 0
        property double fileMtime: 0
        title: "Edit File"
        modal: true
        standardButtons: Dialog.Save | Dialog.Cancel
        anchors.centerIn: parent
        width: 700
        height: 500

        onAccepted: {
            if (editorDialog.isBinary) {
                root.requestNotice("Cannot save binary files through the text editor.")
                return
            }
            // Convert text to base64
            let content = editorField.text
            let contentB64 = btoa(unescape(encodeURIComponent(content)))
            root.backend.writeFileContent(editorDialog.filePath, contentB64, false)
        }

        contentItem: ColumnLayout {
            width: 660
            height: 460
            spacing: 10
            anchors.margins: 16

            // File info header
            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Rectangle {
                    width: 40
                    height: 40
                    radius: 8
                    color: root.colorPrimaryLight
                    Text {
                        anchors.centerIn: parent
                        text: "📝"
                        font.pixelSize: 20
                    }
                }
                ColumnLayout { spacing: 2
                    Label {
                        text: editorDialog.filePath
                        color: root.colorTextPrimary
                        font.pixelSize: 13
                        font.bold: true
                        wrapMode: Text.WrapAnywhere
                    }
                    Label {
                        text: "Size: " + root.formatSize(editorDialog.fileSize)
                            + " | Modified: " + root.formatTime(editorDialog.fileMtime)
                            + (editorDialog.isBinary ? " | Binary file" : " | Text file")
                        color: root.colorTextSecondary
                        font.pixelSize: 11
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: root.colorBorder
            }

            // Editor
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.vertical: ScrollBar { }
                ScrollBar.horizontal: ScrollBar { }
                TextArea {
                    id: editorField
                    width: parent.width
                    height: parent.height
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.NoWrap
                    background: Rectangle {
                        color: root.colorSurface
                        border.color: root.colorBorder
                        border.width: 1
                        radius: 6
                    }
                    padding: 8
                }
            }

            // Warning for binary files
            Label {
                visible: editorDialog.isBinary
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.colorWarning
                font.pixelSize: 11
                text: "⚠ This file appears to be binary. Editing may corrupt it. Save is disabled for binary files."
            }
        }
    }

    // Upload Dialog
    Dialog {
        id: uploadDialog
        property string remotePath: ""
        property string localPath: ""
        property string fileName: ""
        property real progress: 0
        property string progressText: ""
        property bool uploading: false
        title: "Upload File"
        modal: false
        anchors.centerIn: parent
        width: 500

        function resetUpload() {
            localPath = ""
            fileName = ""
            progress = 0
            progressText = ""
            uploading = false
            // FileDialog will be reset when opened
        }

        contentItem: Column {
            width: 460
            spacing: 14
            anchors.margins: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Rectangle {
                    width: 40
                    height: 40
                    radius: 8
                    color: root.colorSuccess
                    opacity: 0.12
                    Text {
                        anchors.centerIn: parent
                        text: "⬆"
                        font.pixelSize: 20
                        color: root.colorSuccess
                    }
                }
                ColumnLayout { spacing: 2
                    Label {
                        text: "Upload File to Server"
                        color: root.colorTextPrimary
                        font.pixelSize: 14
                        font.bold: true
                    }
                    Label {
                        text: "Destination: " + uploadDialog.remotePath
                        color: root.colorTextSecondary
                        font.pixelSize: 11
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.colorBorder
            }

            // File picker button
            Button {
                id: uploadPickBtn
                text: uploadDialog.uploading ? "Uploading..." : "Choose Local File..."
                Layout.fillWidth: true
                height: 40
                font.pixelSize: 13
                enabled: !root.busy && !uploadDialog.uploading
                background: Rectangle {
                    implicitHeight: 40
                    radius: 6
                    color: uploadDialog.uploading ? root.colorTextMuted : root.colorPrimary
                    border.color: uploadDialog.uploading ? root.colorTextMuted : root.colorPrimary
                    border.width: 1
                }
                contentItem: Text {
                    text: uploadDialog.uploading ? "Uploading..." : "Choose Local File..."
                    color: "#ffffff"
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    if (!uploadDialog.uploading) {
                        uploadFileDialog.open()
                    }
                }
            }

            // Show selected file path
            TextField {
                id: uploadPathField
                placeholderText: "No file selected"
                readOnly: true
                height: 36
                font.pixelSize: 12
                padding: 8
                visible: uploadDialog.localPath !== ""
                text: uploadDialog.localPath
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurfaceHover
                    border.color: root.colorBorder
                    border.width: 1
                }
            }

            // Selected file name label
            Label {
                id: uploadFileNameLabel
                visible: uploadDialog.fileName !== "" && !uploadDialog.uploading
                width: parent.width
                text: "Selected: " + uploadDialog.fileName
                color: root.colorTextSecondary
                font.pixelSize: 11
            }

            // Progress indicator (shown during upload)
            Column {
                visible: uploadDialog.uploading
                width: parent.width
                spacing: 8

                // Spinner + status text
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    BusyIndicator {
                        width: 24
                        height: 24
                        running: uploadDialog.uploading
                    }

                    Label {
                        id: uploadStatusText
                        text: uploadDialog.progressText
                        color: root.colorTextPrimary
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                }

                // Progress percentage
                Label {
                    text: Math.round(uploadDialog.progress * 100) + "%"
                    color: root.colorTextPrimary
                    font.pixelSize: 11
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
                // Progress bar
                ProgressBar {
                    id: uploadProgressBar
                    Layout.fillWidth: true
                    height: 10
                    from: 0
                    to: 1
                    value: uploadDialog.progress
                    background: Rectangle {
                        implicitHeight: 10
                        radius: 5
                        color: root.colorSurfaceHover
                        border.color: root.colorBorder
                        border.width: 1
                    }
                    contentItem: Rectangle {
                        implicitHeight: 10
                        radius: 5
                        color: root.colorPrimary
                        width: uploadDialog.progress * parent.width
                    }
                }
            }

            // Completion message
            Label {
                visible: uploadDialog.progress === 1 && !uploadDialog.uploading
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.colorSuccess
                font.pixelSize: 12
                text: "✓ " + uploadDialog.progressText
            }

            // Error message
            Label {
                visible: uploadDialog.progress === 0 && uploadDialog.progressText !== "" && !uploadDialog.uploading
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.colorDanger
                font.pixelSize: 12
                text: "✗ " + uploadDialog.progressText
            }
        }
    }

    // FileDialog for upload - placed at root level to avoid Column layout issues
    FileDialog {
        id: uploadFileDialog
        title: "Select File to Upload"
        nameFilters: ["All Files (*)"]
        fileMode: FileDialog.OpenFile
        onAccepted: {
            var urls = uploadFileDialog.selectedFiles
            if (urls && urls.length > 0) {
                let localPath = urls[0].toString()
                if (localPath.startsWith("file:///")) {
                    localPath = localPath.substring(8)
                } else if (localPath.startsWith("file://")) {
                    localPath = localPath.substring(7)
                }
                localPath = decodeURIComponent(localPath)
                uploadDialog.localPath = localPath
                uploadDialog.fileName = fileNameFromPath(localPath)
                uploadDialog.progress = 0
                uploadDialog.progressText = "Preparing to upload " + uploadDialog.fileName + "…"
                // Show upload progress dialog and start upload
                uploadDialog.uploading = true
                uploadDialog.open()
                let remotePath = uploadDialog.remotePath
                if (!remotePath.endsWith("/")) remotePath += "/"
                root.backend.uploadFile(localPath, remotePath + uploadDialog.fileName)
            }
        }
    }

    // Download Dialog
    Dialog {
        id: downloadDialog
        property string remotePath: ""
        property string remoteFileName: ""
        property string localPath: ""
        property string localFileName: ""
        property real progress: 0
        property string progressText: ""
        property bool downloading: false
        title: "Download File"
        modal: true
        anchors.centerIn: parent
        width: 500

        function startDownload() {
            if (downloadDialog.remotePath && downloadDialog.localPath) {
                downloadDialog.downloading = true
                root.backend.downloadFile(downloadDialog.remotePath, downloadDialog.localPath)
            }
        }

        function resetDownload() {
            localPath = ""
            progress = 0
            progressText = ""
            downloading = false
            // Populate with default save path (downloads folder + remote file name)
            if (root.backend && downloadDialog.remoteFileName) {
                localPath = root.backend.defaultDownloadDir() + "/" + downloadDialog.remoteFileName
            }
        }

        contentItem: Column {
            width: 460
            spacing: 14
            anchors.margins: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Rectangle {
                    width: 40
                    height: 40
                    radius: 8
                    color: root.colorPrimaryLight
                    Text {
                        anchors.centerIn: parent
                        text: "⬇"
                        font.pixelSize: 20
                        color: root.colorPrimary
                    }
                }
                ColumnLayout { spacing: 2
                    Label {
                        text: "Download File from Server"
                        color: root.colorTextPrimary
                        font.pixelSize: 14
                        font.bold: true
                    }
                    Label {
                        text: "Source: " + downloadDialog.remotePath
                        color: root.colorTextSecondary
                        font.pixelSize: 11
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: root.colorBorder
            }

            // Save location
            Label { text: "Save to:"; font.pixelSize: 12; color: root.colorTextSecondary }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                TextField {
                    id: downloadPathField
                    placeholderText: "Choose save location..."
                    readOnly: true
                    height: 36
                    font.pixelSize: 12
                    padding: 8
                    Layout.fillWidth: true
                    text: downloadDialog.localPath
                    background: Rectangle {
                        implicitHeight: 36
                        radius: 6
                        color: root.colorSurfaceHover
                        border.color: root.colorBorder
                        border.width: 1
                    }
                }

                Button {
                    id: downloadPickBtn
                    text: "Choose save location..."
                    height: 36
                    font.pixelSize: 12
                    enabled: !root.busy && !downloadDialog.downloading
                    background: Rectangle {
                        implicitHeight: 36
                        radius: 6
                        color: root.colorPrimary
                        border.color: root.colorPrimary
                        border.width: 1
                    }
                    contentItem: Text {
                        text: "Choose save location..."
                        color: "#ffffff"
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!downloadDialog.downloading) {
                            // Pre-fill the Save As dialog with the current save path
                            // so the user sees both the folder and filename
                            if (downloadDialog.localPath) {
                                downloadFileDialog.selectedFile = Qt.url("file:///" + downloadDialog.localPath)
                            }
                            downloadFileDialog.open()
                        }
                    }
                }
            }

            // Progress indicator (shown during download)
            Column {
                visible: downloadDialog.downloading
                width: parent.width
                spacing: 8

                // Spinner + status text
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    BusyIndicator {
                        width: 24
                        height: 24
                        running: downloadDialog.downloading
                    }

                    Label {
                        id: downloadStatusText
                        text: downloadDialog.progressText
                        color: root.colorTextPrimary
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                }

                // Progress percentage
                Label {
                    text: Math.round(downloadDialog.progress * 100) + "%"
                    color: root.colorTextPrimary
                    font.pixelSize: 11
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
                // Progress bar
                ProgressBar {
                    id: downloadProgressBar
                    Layout.fillWidth: true
                    height: 10
                    from: 0
                    to: 1
                    value: downloadDialog.progress
                    background: Rectangle {
                        implicitHeight: 10
                        radius: 5
                        color: root.colorSurfaceHover
                        border.color: root.colorBorder
                        border.width: 1
                    }
                    contentItem: Rectangle {
                        implicitHeight: 10
                        radius: 5
                        color: root.colorPrimary
                        width: downloadDialog.progress * parent.width
                    }
                }
            }

            // Completion message
            Label {
                visible: downloadDialog.progress === 1 && !downloadDialog.downloading
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.colorSuccess
                font.pixelSize: 12
                text: "✓ " + downloadDialog.progressText
            }

            // Error message
            Label {
                visible: downloadDialog.progress === 0 && downloadDialog.progressText !== "" && !downloadDialog.downloading
                width: parent.width
                wrapMode: Text.WordWrap
                color: root.colorDanger
                font.pixelSize: 12
                text: "✗ " + downloadDialog.progressText
            }
        }

        footer: RowLayout {
            Layout.fillWidth: true
            spacing: 10

            // Download button - shown when not downloading and not yet started
            Button {
                id: downloadBtn
                visible: !downloadDialog.downloading && downloadDialog.progress === 0
                text: "Download"
                Layout.fillWidth: true
                height: 36
                enabled: downloadDialog.remotePath && downloadDialog.localPath
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorPrimary
                    border.color: root.colorPrimary
                    border.width: 1
                }
                contentItem: Text {
                    text: "Download"
                    color: "#ffffff"
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: downloadDialog.startDownload()
            }

            // Close button - shown when download completes (success or failure)
            Button {
                id: downloadCloseBtn
                visible: !downloadDialog.downloading && (
                    downloadDialog.progress === 1
                    || (downloadDialog.progress === 0 && downloadDialog.progressText !== "")
                )
                text: "Close"
                Layout.fillWidth: true
                height: 36
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorPrimary
                    border.color: root.colorPrimary
                    border.width: 1
                }
                contentItem: Text {
                    text: "Close"
                    color: "#ffffff"
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: downloadDialog.close()
            }

            // Cancel button - shown while downloading
            Button {
                id: downloadCancelBtn
                visible: downloadDialog.downloading
                text: "Cancel"
                Layout.fillWidth: true
                height: 36
                enabled: !root.busy
                background: Rectangle {
                    implicitHeight: 36
                    radius: 6
                    color: root.colorSurfaceHover
                    border.color: root.colorBorder
                    border.width: 1
                }
                contentItem: Text {
                    text: "Cancel"
                    color: root.colorTextPrimary
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    // Request abort from the backend; onDownloadCompleted
                    // will finalize the UI once the transfer actually stops.
                    if (root.backend) root.backend.cancelDownload()
                    downloadDialog.downloading = false
                    downloadDialog.progress = 0
                    downloadDialog.progressText = ""
                    downloadDialog.close()
                }
            }
        }
    }

    // FileDialog for download - placed at root level to avoid Column layout issues
    FileDialog {
        id: downloadFileDialog
        title: "Choose Save Location"
        nameFilters: ["All Files (*)"]
        fileMode: FileDialog.SaveFile
        onAccepted: {
            var urls = downloadFileDialog.selectedFiles
            if (urls && urls.length > 0) {
                let localPath = urls[0].toString()
                if (localPath.startsWith("file:///")) {
                    localPath = localPath.substring(8)
                } else if (localPath.startsWith("file://")) {
                    localPath = localPath.substring(7)
                }
                localPath = decodeURIComponent(localPath)
                // localPath is the full save path (folder + filename) chosen in the Save As dialog
                downloadDialog.localPath = localPath
                downloadPathField.text = localPath
            }
        }
    }

}