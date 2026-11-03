pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property var backend: null
    property bool busy: false
    property string theme: "light"
    signal requestNotice(string message)

    // Theme-aware color palette ("system" resolves to light for now).
    readonly property color colorPrimary: theme === "dark" ? "#3b82f6" : "#2563eb"
    readonly property color colorPrimaryHover: theme === "dark" ? "#60a5fa" : "#1d4ed8"
    readonly property color colorPrimaryLight: theme === "dark" ? "#1e3a8a" : "#dbeafe"
    readonly property color colorDanger: theme === "dark" ? "#f87171" : "#dc2626"
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

    function formatSize(bytes) {
        if (!bytes)
            return "0 B"
        if (bytes < 1024)
            return bytes + " B"
        if (bytes < 1024 * 1024)
            return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024)
            return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        if (bytes < 1024 * 1024 * 1024 * 1024)
            return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB"
        return (bytes / (1024 * 1024 * 1024 * 1024)).toFixed(2) + " TB"
    }

    function isWarning(percent) {
        return percent >= 90
    }

    function isCritical(percent) {
        return percent >= 95
    }

    function usageColor(percent) {
        if (percent >= 95) return root.colorDanger
        if (percent >= 90) return root.colorWarning
        if (percent >= 70) return root.colorPrimary
        return root.colorSuccess
    }

    ListModel { id: diskModel }
    ListModel { id: deviceModel }

    Connections {
        target: root.backend

        function onDiskUsageLoaded(rows) {
            diskModel.clear()
            for (let i = 0; i < rows.length; ++i) {
                diskModel.append({
                    device: rows[i].device || "",
                    mount: rows[i].mount || "",
                    size: rows[i].size || 0,
                    used: rows[i].used || 0,
                    available: rows[i].available || 0,
                    usePercent: rows[i].used_percent || 0,
                    inodesTotal: rows[i].inodes || 0,
                    inodesUsed: rows[i].inodes_used || 0,
                    inodesFree: rows[i].inodes_free || 0,
                    inodesUsedPercent: rows[i].inodes_used_percent || 0,
                })
            }
        }

        function onBlockDevicesLoaded(rows) {
            deviceModel.clear()
            for (let i = 0; i < rows.length; ++i) {
                deviceModel.append({
                    name: rows[i].name || "",
                    type: rows[i].type || "",
                    size: rows[i].size || 0,
                    fstype: rows[i].fstype || "",
                    mount: rows[i].mount || "",
                    label: rows[i].label || "",
                })
            }
        }

        function onErrorOccurred(message) {
            root.requestNotice("Disk operations failed:\n" + message)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        // Header
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
                    color: root.colorPrimaryLight
                    Text {
                        anchors.centerIn: parent
                        text: "💾"
                        font.pixelSize: 18
                        color: root.colorPrimary
                    }
                }
                ColumnLayout { spacing: 0
                    Label {
                        text: "Disk Usage & Block Devices"
                        font.pixelSize: 18
                        font.bold: true
                        color: root.colorTextPrimary
                    }
                    Label {
                        text: "Monitor filesystem space, inode usage, and block devices on the remote server"
                        font.pixelSize: 12
                        color: root.colorTextSecondary
                    }
                }
                Item { Layout.fillWidth: true }

                RowLayout { spacing: 8
                    Button {
                        text: "Refresh Disk Usage"
                        enabled: !root.busy && root.backend !== null
                        onClicked: root.backend.loadDiskUsage()
                        height: 36
                        font.pixelSize: 12
                        background: Rectangle {
                            implicitHeight: 36
                            radius: 6
                            color: root.colorPrimary
                            border.color: root.colorPrimary
                            border.width: 1
                        }
                        contentItem: Text {
                            text: "Refresh Disk Usage"
                            color: "#ffffff"
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    Button {
                        text: "Refresh Devices"
                        enabled: !root.busy && root.backend !== null
                        onClicked: root.backend.loadBlockDevices()
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
            }
        }

        // Filesystem Usage Section
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 280
            color: root.colorSurface
            border.color: root.colorBorder
            border.width: 1
            radius: 8

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Section Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 48
                    radius: 8
                    color: root.colorBg
                    border.color: root.colorBorder
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        Label {
                            text: "Mounted Filesystems"
                            font.bold: true
                            color: root.colorTextPrimary
                            font.pixelSize: 13
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: diskModel.count + " filesystems"
                            color: root.colorTextMuted
                            font.pixelSize: 11
                        }
                    }
                }

                // Table Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 36
                    color: root.colorBg
                    border.color: root.colorBorder
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8
                        Label { text: "Device"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 120 }
                        Label { text: "Mount Point"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                        Label { text: "Used / Total"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 140; horizontalAlignment: Text.AlignRight }
                        Label { text: "Free"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 100; horizontalAlignment: Text.AlignRight }
                        Label { text: "Space %"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 70; horizontalAlignment: Text.AlignRight }
                        Label { text: "Inodes"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 140 }
                    }
                }

                // Filesystem List
                ListView {
                    id: diskList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: diskModel
                    spacing: 0
                    ScrollBar.vertical: ScrollBar {}

                    delegate: Rectangle {
                        required property string device
                        required property string mount
                        required property real size
                        required property real used
                        required property real available
                        required property int usePercent
                        required property int inodesTotal
                        required property int inodesFree
                        required property int inodesUsedPercent
                        width: ListView.view.width
                        height: 44
                        color: "transparent"
                        border.color: root.colorBorder
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Label {
                                text: device || "—"
                                color: root.colorTextPrimary
                                font.family: "monospace"
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                                Layout.preferredWidth: 120
                            }
                            Label {
                                text: mount || "—"
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                                Layout.preferredWidth: 140
                            }
                            Label {
                                text: root.formatSize(used) + " / " + root.formatSize(size)
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                Layout.preferredWidth: 140
                                horizontalAlignment: Text.AlignRight
                            }
                            Label {
                                text: root.formatSize(available)
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                Layout.preferredWidth: 100
                                horizontalAlignment: Text.AlignRight
                            }
                            // Usage Bar with Percentage
                            Rectangle {
                                Layout.preferredWidth: 70
                                Layout.preferredHeight: 20
                                radius: 10
                                color: root.colorBorder

                                Rectangle {
                                    id: usageBar
                                    height: parent.height
                                    width: Math.max(0, (usePercent / 100) * parent.width)
                                    radius: 10
                                    color: root.usageColor(usePercent)
                                    Behavior on width { NumberAnimation { duration: 300 } }
                                }

                                Label {
                                    anchors.centerIn: parent
                                    text: usePercent + "%"
                                    font.pixelSize: 10
                                    font.bold: true
                                    color: usePercent > 50 ? "#ffffff" : root.colorTextPrimary
                                }
                            }
                            Label {
                                text: inodesTotal > 0
                                    ? inodesFree + " free of " + inodesTotal
                                      + " (" + inodesUsedPercent + "% used)"
                                    : "not reported"
                                color: root.isWarning(inodesUsedPercent) ? root.colorWarning : root.colorTextSecondary
                                font.pixelSize: 11
                                Layout.preferredWidth: 140
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    anchors.margins: 16
                    visible: diskModel.count === 0
                    text: "No filesystem data yet. Click 'Refresh Disk Usage'."
                    color: root.colorTextMuted
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        // Block Devices Section
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 220
            color: root.colorSurface
            border.color: root.colorBorder
            border.width: 1
            radius: 8

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Section Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 48
                    radius: 8
                    color: root.colorBg
                    border.color: root.colorBorder
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        Label {
                            text: "Disks & Partitions"
                            font.bold: true
                            color: root.colorTextPrimary
                            font.pixelSize: 13
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: deviceModel.count + " devices"
                            color: root.colorTextMuted
                            font.pixelSize: 11
                        }
                    }
                }

                // Table Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 36
                    color: root.colorBg
                    border.color: root.colorBorder
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8
                        Label { text: "Device"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 100 }
                        Label { text: "Type"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 80 }
                        Label { text: "Size"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 100; horizontalAlignment: Text.AlignRight }
                        Label { text: "File System"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 100 }
                        Label { text: "Mount Point"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.fillWidth: true }
                        Label { text: "Label"; font.bold: true; color: root.colorTextSecondary; font.pixelSize: 11; Layout.preferredWidth: 100 }
                    }
                }

                // Device List
                ListView {
                    id: deviceList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: deviceModel
                    spacing: 0
                    ScrollBar.vertical: ScrollBar {}

                    delegate: Rectangle {
                        required property string name
                        required property string type
                        required property real size
                        required property string fstype
                        required property string mount
                        required property string label
                        width: ListView.view.width
                        height: 40
                        color: "transparent"
                        border.color: root.colorBorder
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Label {
                                text: name || "—"
                                color: root.colorTextPrimary
                                font.bold: true
                                font.family: "monospace"
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                                Layout.preferredWidth: 100
                            }
                            Label {
                                text: type || "—"
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                                Layout.preferredWidth: 80
                            }
                            Label {
                                text: root.formatSize(size)
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                Layout.preferredWidth: 100
                                horizontalAlignment: Text.AlignRight
                            }
                            Label {
                                text: fstype || "—"
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                                Layout.preferredWidth: 100
                            }
                            Label {
                                text: mount || "—"
                                color: root.colorTextSecondary
                                font.pixelSize: 11
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                            Label {
                                text: label || "—"
                                color: root.colorTextMuted
                                font.pixelSize: 11
                                Layout.preferredWidth: 100
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    anchors.margins: 16
                    visible: deviceModel.count === 0
                    text: "No device data yet. Click 'Refresh Devices'."
                    color: root.colorTextMuted
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}