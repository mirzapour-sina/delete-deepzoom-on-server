pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property var backend: null
    property bool busy: false
    property string currentPath: ""
    property string theme: "light"

    signal requestNotice(string message)
    signal requestConfirm(string title, string message, var callback)

    function selectedPaths() {
        let result = []
        for (let i = 0; i < folderModel.count; ++i) {
            let item = folderModel.get(i)
            if (item.selected)
                result.push(item.path)
        }
        return result
    }

    function setAllSelected(selected) {
        for (let i = 0; i < folderModel.count; ++i)
            folderModel.setProperty(i, "selected", selected)
    }

    property string themeLight: "light"

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

    Component.onCompleted: {
        if (root.backend) {
            var savedTheme = root.backend.getTheme()
            if (savedTheme === "light" || savedTheme === "dark")
                root.theme = savedTheme
        }
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
        root.backend.connectAndLoad(
            root.backend._settings?.host || "",
            root.backend._settings?.username || "",
            String(root.backend._settings?.port || 22),
            path,
            root.backend._settings?.key_filename || "",
            root.backend._settings?.password || ""
        )
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

    function requireBackend() {
        if (root.backend === null) {
            root.requestNotice("Connect to the server first.")
            return false
        }
        return true
    }

    ListModel { id: folderModel }

    Connections {
        target: root.backend

        function onFoldersLoaded(folders) {
            folderModel.clear()
            for (let i = 0; i < folders.length; ++i) {
                folderModel.append({
                    name: folders[i].name,
                    path: folders[i].path,
                    selected: false
                })
            }
            // Update current path from the first folder's parent
            if (folders.length > 0) {
                let firstPath = folders[0].path
                let parts = firstPath.split("/").filter(function (part) { return part.length > 0 })
                parts.pop()
                root.currentPath = "/" + parts.join("/")
                pathField.text = root.currentPath
            }
        }

        function onFoldersRemoved(paths) {
            for (let i = folderModel.count - 1; i >= 0; --i) {
                if (paths.indexOf(folderModel.get(i).path) !== -1)
                    folderModel.remove(i)
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        // Header card
        Rectangle {
            Layout.fillWidth: true
            height: 56
            radius: 8
            color: root.colorSurface
            border.color: root.colorBorder
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Rectangle {
                    width: 36
                    height: 36
                    radius: 8
                    color: root.colorDanger
                    opacity: 0.12
                    Text {
                        anchors.centerIn: parent
                        text: "🗑"
                        font.pixelSize: 18
                        color: root.colorDanger
                    }
                }

                Label {
                    text: "Choose DeepZoom folders to remove. Deletion runs on the Linux server and cannot be undone."
                    color: root.colorTextSecondary
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: 13
                }
            }
        }

        // Path Bar
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                id: upBtn
                text: "↑ Up"
                enabled: !root.busy && root.currentPath !== "" && root.currentPath !== "/"
                onClicked: root.goUp()
                Layout.preferredHeight: 40
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 40
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
                Layout.preferredHeight: 40
                font.pixelSize: 13
                padding: 10
                onAccepted: root.goTo(pathField.text)
                background: Rectangle {
                    implicitHeight: 40
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
                Layout.preferredHeight: 40
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 40
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Refresh"
                enabled: !root.busy && root.currentPath !== ""
                onClicked: {
                    if (root.backend && root.backend._settings) {
                        root.backend.connectAndLoad(
                            root.backend._settings.host,
                            root.backend._settings.username,
                            String(root.backend._settings.port),
                            root.currentPath,
                            root.backend._settings.key_filename || "",
                            root.backend._settings.password || ""
                        )
                    }
                }
                Layout.preferredHeight: 40
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 40
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
        }

        // Toolbar
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                text: "Select All"
                enabled: !root.busy && folderModel.count > 0
                onClicked: root.setAllSelected(true)
                Layout.preferredHeight: 40
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 40
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Button {
                text: "Select None"
                enabled: !root.busy && folderModel.count > 0
                onClicked: root.setAllSelected(false)
                Layout.preferredHeight: 40
                font.pixelSize: 12
                background: Rectangle {
                    implicitHeight: 40
                    radius: 6
                    color: root.colorSurface
                    border.color: root.colorBorder
                    border.width: 1
                }
            }
            Item { Layout.fillWidth: true }
            Label {
                text: folderModel.count + " folder(s) loaded"
                color: root.colorTextMuted
                font.pixelSize: 12
                Layout.alignment: Qt.AlignVCenter
            }
        }

        // Folder List
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.colorSurface
            border.color: root.colorBorder
            border.width: 1
            radius: 8

            ScrollView {
                anchors.fill: parent
                anchors.margins: 4
                clip: true

                Column {
                    width: parent.width
                    spacing: 1

                    Repeater {
                        model: folderModel
                        delegate: RowLayout {
                            id: folderRow
                            required property string name
                            required property string path
                            required property bool selected
                            required property int index
                            width: parent.width
                            spacing: 12
                            height: 48

                            Rectangle {
                                width: 48
                                height: 48
                                radius: 8
                                color: folderRow.selected ? root.colorPrimaryLight : root.colorSurfaceHover
                                border.color: folderRow.selected ? root.colorPrimary : root.colorBorder
                                border.width: folderRow.selected ? 2 : 1

                                CheckBox {
                                    anchors.centerIn: parent
                                    checked: folderRow.selected
                                    enabled: !root.busy
                                    onToggled: folderModel.setProperty(folderRow.index, "selected", checked)
                                }
                            }

                            Label {
                                text: folderRow.path
                                color: root.colorTextPrimary
                                wrapMode: Text.WrapAnywhere
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                font.pixelSize: 12
                            }
                        }
                    }

                    Label {
                        visible: folderModel.count === 0
                        width: parent.width
                        padding: 24
                        text: "No folders loaded. Connect to a server to browse."
                        color: root.colorTextMuted
                        horizontalAlignment: Text.AlignHCenter
                        font.pixelSize: 13
                    }
                }
            }
        }

        // Action Bar
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: root.selectedPaths().length + " folder(s) selected"
                color: root.colorTextSecondary
                font.pixelSize: 12
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
            }
            Button {
                text: "Remove Selected"
                enabled: !root.busy && root.selectedPaths().length > 0
                font.pixelSize: 12
                font.bold: true
                Layout.preferredHeight: 40
                background: Rectangle {
                    implicitHeight: 40
                    radius: 6
                    color: root.busy ? root.colorTextMuted : root.colorDanger
                    border.color: root.busy ? root.colorTextMuted : root.colorDanger
                    border.width: 1
                }
                contentItem: Text {
                    text: "Remove Selected"
                    color: "#ffffff"
                    font.pixelSize: 12
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    root.requestConfirm(
                        "Confirm Permanent Deletion",
                        "Permanently delete " + root.selectedPaths().length +
                        " selected folder(s) from the Linux server?\n\nThis cannot be undone.",
                        function() { root.backend.removeFolders(root.selectedPaths()) }
                    )
                }
            }
        }
    }
}
