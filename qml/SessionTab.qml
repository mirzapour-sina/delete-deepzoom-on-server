pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs

Item {
    id: root
    anchors.fill: parent

    property var backend: null
    property int sessionIndex: -1
    property string sessionName: "New Session"
    property string host: ""
    property int port: 22
    property string username: ""
    property string remotePath: "/"
    property string statusMessage: "Not connected"
    property string connectionStatus: "disconnected"
    property bool connected: false
    property var connectionHistory: []
    property string sshKeyPath: ""
    property string password: ""

    signal closeRequested()
    signal sessionConnectionStatusChanged(string status, string message)
    signal requestNotice(string message)
    signal requestConfirm(string title, string message, var callback)
    signal requestConnect()
    // Request the shell to open the shared "Manage Saved Connections" dialog.
    signal manageConnectionsRequested()

    property bool connecting: false
    property bool savePassword: false
    property string theme: "light"

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
            root.backend.loadConnectionHistory()
            root.connectionHistory = root.backend.getConnectionHistory()
            var last = root.backend.getLastConnection()
            if (last && last.host) {
                hostFieldInput.text = last.host
                portFieldInput.text = String(last.port || 22)
                usernameFieldInput.text = last.username || ""
                pathFieldInput.text = last.remote_path || "/"
                keyFieldInput.text = last.key_filename || ""
            }
            // Apply the saved UI theme.
            var savedTheme = root.backend.getTheme()
            if (savedTheme === "light" || savedTheme === "dark")
                root.theme = savedTheme
        }
    }

    function connectionStatusColor() {
        switch (root.connectionStatus) {
        case "connected": return root.colorSuccess
        case "connecting": return root.colorWarning
        case "host_key_required": return root.colorWarning
        case "disconnected": return root.colorTextMuted
        default: return root.colorTextMuted
        }
    }

    function connectionStatusText() {
        switch (root.connectionStatus) {
        case "connected": return "● Connected"
        case "connecting": return "● Connecting…"
        case "host_key_required": return "● Verify Host Key"
        case "disconnected": return "○ Disconnected"
        default: return "○ Unknown"
        }
    }

    function doConnect() {
        if (!hostFieldInput.text || !usernameFieldInput.text || !pathFieldInput.text) {
            root.requestNotice("Please fill in all required fields")
            return
        }
        connecting = true
        root.host = hostFieldInput.text
        root.port = parseInt(portFieldInput.text)
        root.username = usernameFieldInput.text
        root.remotePath = pathFieldInput.text
        root.sshKeyPath = keyFieldInput.text
        root.password = passwordFieldInput.text
        root.backend.connectAndLoad(
            hostFieldInput.text,
            usernameFieldInput.text,
            portFieldInput.text,
            pathFieldInput.text,
            keyFieldInput.text,
            passwordFieldInput.text,
            root.savePassword
        )
    }

    function loadConnectionProfile(profile) {
        if (!profile) return
        hostFieldInput.text = profile.host
        portFieldInput.text = profile.port
        usernameFieldInput.text = profile.username
        pathFieldInput.text = profile.remote_path
        keyFieldInput.text = profile.key_filename || ""
        passwordFieldInput.text = profile.password || ""
        root.savePassword = profile.password ? true : false
    }

    Connections {
        target: root.backend

        function onBusyChanged(value) {
            // Forward to parent via requestNotice if needed
        }

        function onErrorOccurred(message) {
            root.requestNotice(message)
        }

        function onStatusChanged(message) {
            root.statusMessage = message
        }

        function onClipboardChanged(operation, count) {
            // Could emit a signal if needed
        }

        function onHostKeyTrustRequested(host, port, fingerprint) {
            hostTrustDialog.serverAddress = host + ":" + port
            hostTrustDialog.fingerprint = fingerprint
            hostTrustDialog.open()
        }

        function onConnectionStatusChanged(status, message) {
            root.connectionStatus = status
            root.statusMessage = message
            root.connected = (status === "connected")
            // Only stop showing the connect overlay on final states;
            // "connecting" is an intermediate state and must keep the spinner visible.
            if (status === "connected" || status === "disconnected" || status === "host_key_required")
                connecting = false
            root.sessionConnectionStatusChanged(status, message)
        }

        function onConnectionHistoryLoaded(history) {
            root.connectionHistory = history
        }

        function onConnectionSaved(hostKey) {
        }

        function onConnectionRemoved(hostKey) {
        }

        function onFileContentLoaded(path, info) {
            root.requestNotice("File loaded: " + path)
        }

        function onFileWritten(path, success, message) {
            if (success) {
                root.requestNotice("File saved: " + path)
            } else {
                root.requestNotice("Failed to save: " + message)
            }
        }

        function onUploadProgress(filename, current, total) {
        }

        function onDownloadProgress(filename, current, total) {
        }

        function onUploadCompleted(remotePath, success, message) {
            root.statusMessage = success
                ? ("Uploaded: " + remotePath)
                : ("Upload failed: " + message)
        }

        function onDownloadCompleted(localPath, success, message) {
            root.statusMessage = success
                ? ("Downloaded: " + localPath)
                : ("Download failed: " + message)
        }
    }

    // ------------------------------------------------------------------
    // Disconnected state - connection form inside a polished card
    // ------------------------------------------------------------------
    Item {
        id: disconnectedView
        anchors.fill: parent
        visible: !root.connected

        Column {
            anchors.fill: parent
            anchors.margins: 40
            spacing: 24

            // Header
            Column {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                Rectangle {
                    width: 72
                    height: 72
                    radius: 36
                    color: root.colorPrimaryLight
                    Text {
                        anchors.centerIn: parent
                        text: "🔐"
                        font.pixelSize: 32
                    }
                }

                Label {
                    text: "New SSH Session"
                    font.pixelSize: 20
                    font.bold: true
                    color: root.colorTextPrimary
                }

                Label {
                    width: 420
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    text: "Enter your SSH connection details to connect to a Linux server"
                    font.pixelSize: 13
                    color: root.colorTextSecondary
                }
            }

            // Connection form card
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 520
                height: 480
                radius: 12
                color: root.colorSurface
                border.color: root.colorBorder
                border.width: 1

                Column {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 16

                    // Saved Connections dropdown
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Label {
                            text: "Saved Connections"
                            font.pixelSize: 12
                            color: root.colorTextSecondary
                            Layout.alignment: Qt.AlignLeft
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            ComboBox {
                                id: historyCombo
                                objectName: "historyCombo"
                                model: root.connectionHistory
                                textRole: "displayText"
                                Layout.fillWidth: true
                                Layout.minimumWidth: 200
                                currentIndex: -1
                                onActivated: (idx) => {
                                    if (idx >= 0 && idx < root.connectionHistory.length) {
                                        var profile = root.connectionHistory[idx]
                                        loadConnectionProfile(profile)
                                    }
                                }
                                delegate: ItemDelegate {
                                    required property var modelData
                                    required property int index
                                    width: parent.width
                                    text: modelData.displayText !== undefined ? modelData.displayText : modelData.host
                                    font.pixelSize: 12
                                    contentItem: Text {
                                        text: modelData.displayText !== undefined ? modelData.displayText : modelData.host
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                    background: Rectangle {
                                        implicitHeight: 40
                                        color: "transparent"
                                    }
                                }
                                background: Rectangle {
                                    implicitHeight: 40
                                    radius: 8
                                    color: root.colorSurface
                                    border.color: root.colorBorder
                                    border.width: 1
                                }
                            }

                            Button {
                                text: "Manage"
                                flat: true
                                enabled: root.connectionHistory.length > 0
                                font.pixelSize: 12
                                height: 40
                                background: Rectangle {
                                    implicitHeight: 40
                                    radius: 6
                                    color: root.colorSurface
                                    border.color: root.colorBorder
                                    border.width: 1
                                }
                                contentItem: Text {
                                    text: "Manage"
                                    color: root.colorPrimary
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                onClicked: root.manageConnectionsRequested()
                            }
                        }
                    }

                    Rectangle {
                        width: parent.width
                        height: 1
                        color: root.colorBorder
                    }

                    // Connection form grid
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 14

                        // Row 1: Server (full width)
                        Label { text: "Server"; font.pixelSize: 12; color: root.colorTextSecondary }
                        TextField {
                            id: hostFieldInput
                            objectName: "hostFieldInput"
                            placeholderText: "host or IP address"
                            Layout.fillWidth: true
                            Layout.columnSpan: 2
                            padding: 10
                            font.pixelSize: 13
                            Component.onCompleted: {
                                if (contentItem) contentItem.layoutDirection = Qt.LeftToRight
                            }
                            background: Rectangle {
                                implicitHeight: 40
                                radius: 8
                                color: root.colorSurface
                                border.color: root.colorBorder
                                border.width: 1
                            }
                        }

                        // Row 2: Port, Username
                        Label { text: "Port"; font.pixelSize: 12; color: root.colorTextSecondary }
                        TextField {
                            id: portFieldInput
                            objectName: "portFieldInput"
                            text: "22"
                            inputMethodHints: Qt.ImhDigitsOnly
                            Layout.preferredWidth: 100
                            padding: 10
                            font.pixelSize: 13
                            Component.onCompleted: {
                                if (contentItem) contentItem.layoutDirection = Qt.LeftToRight
                            }
                            background: Rectangle {
                                implicitHeight: 40
                                radius: 8
                                color: root.colorSurface
                                border.color: root.colorBorder
                                border.width: 1
                            }
                        }
                        Label { text: "Username"; font.pixelSize: 12; color: root.colorTextSecondary }
                        TextField {
                            id: usernameFieldInput
                            objectName: "usernameFieldInput"
                            text: "root"
                            placeholderText: "Linux username"
                            Layout.fillWidth: true
                            padding: 10
                            font.pixelSize: 13
                            Component.onCompleted: {
                                if (contentItem) contentItem.layoutDirection = Qt.LeftToRight
                            }
                            background: Rectangle {
                                implicitHeight: 40
                                radius: 8
                                color: root.colorSurface
                                border.color: root.colorBorder
                                border.width: 1
                            }
                        }

                        // Row 3: Password, Remote Path
                        Label { text: "Password"; font.pixelSize: 12; color: root.colorTextSecondary }
                        TextField {
                            id: passwordFieldInput
                            objectName: "passwordFieldInput"
                            placeholderText: "Optional; leave blank for key/agent auth"
                            echoMode: TextInput.Password
                            Layout.fillWidth: true
                            padding: 10
                            font.pixelSize: 13
                            Component.onCompleted: {
                                if (contentItem) contentItem.layoutDirection = Qt.LeftToRight
                            }
                            background: Rectangle {
                                implicitHeight: 40
                                radius: 8
                                color: root.colorSurface
                                border.color: root.colorBorder
                                border.width: 1
                            }
                        }
                        Label { text: "Remote Path"; font.pixelSize: 12; color: root.colorTextSecondary }
                        TextField {
                            id: pathFieldInput
                            objectName: "pathFieldInput"
                            text: "/"
                            placeholderText: "Remote path (default: /)"
                            Layout.fillWidth: true
                            padding: 10
                            font.pixelSize: 13
                            Component.onCompleted: {
                                if (contentItem) contentItem.layoutDirection = Qt.LeftToRight
                            }
                            background: Rectangle {
                                implicitHeight: 40
                                radius: 8
                                color: root.colorSurface
                                border.color: root.colorBorder
                                border.width: 1
                            }
                        }

                        // Row 4: SSH Key (full width)
                        Label { text: "SSH Key"; font.pixelSize: 12; color: root.colorTextSecondary }
                        TextField {
                            id: keyFieldInput
                            objectName: "keyFieldInput"
                            placeholderText: "Optional; otherwise use SSH agent/default key"
                            Layout.fillWidth: true
                            Layout.columnSpan: 2
                            padding: 10
                            font.pixelSize: 13
                            Component.onCompleted: {
                                if (contentItem) contentItem.layoutDirection = Qt.LeftToRight
                            }
                            background: Rectangle {
                                implicitHeight: 40
                                radius: 8
                                color: root.colorSurface
                                border.color: root.colorBorder
                                border.width: 1
                            }
                        }

                        // Row 5: Save password option
                        CheckBox {
                            text: "Save password in history"
                            checked: root.savePassword
                            font.pixelSize: 12
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            onToggled: root.savePassword = checked
                        }
                    }

                    // Connect button
                    Button {
                        id: connectBtn
                        objectName: "connectBtn"
                        Layout.fillWidth: true
                        height: 44
                        font.pixelSize: 13
                        font.bold: true
                        enabled: !connecting && hostFieldInput.text && usernameFieldInput.text && pathFieldInput.text
                        background: Rectangle {
                            implicitHeight: 44
                            radius: 8
                            color: connecting ? root.colorTextMuted : root.colorPrimary
                            border.color: connecting ? root.colorTextMuted : root.colorPrimary
                            border.width: 1
                        }
                        contentItem: Text {
                            text: connecting ? "Connecting…" : "Connect"
                            color: "#ffffff"
                            font.pixelSize: 13
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: doConnect()
                    }
                }
            }
        }

        // Loading overlay shown while connecting
        Rectangle {
            visible: connecting || (root.backend && root.backend.busy)
            anchors.fill: parent
            color: "black"
            opacity: 0.55

            MouseArea {
                anchors.fill: parent
                enabled: true
            }

            Column {
                anchors.centerIn: parent
                spacing: 16

                BusyIndicator {
                    width: 56
                    height: 56
                }

                Label {
                    text: root.connecting
                        ? ("Connecting to " + root.host + ":" + root.port + "…")
                        : ("Processing…")
                    color: "#ffffff"
                    font.pixelSize: 16
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // Connected view - TabBar + Content
    // ------------------------------------------------------------------
    Item {
        id: connectedView
        anchors.fill: parent
        visible: root.connected

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Tab Bar for this session
            TabBar {
                id: sessionTabBar
                Layout.fillWidth: true
                contentHeight: 32

                TabButton {
                    text: "File Explorer"
                    font.pixelSize: 11
                    font.bold: sessionTabBar.currentIndex === 0
                    background: Rectangle {
                        implicitHeight: 32
                        color: sessionTabBar.currentIndex === 0 ? root.colorPrimary : "transparent"
                        border.color: root.colorBorder
                        border.width: sessionTabBar.currentIndex === 0 ? 0 : 1
                    }
                    contentItem: Text {
                        text: "File Explorer"
                        color: sessionTabBar.currentIndex === 0 ? "#ffffff" : root.colorTextPrimary
                        font.pixelSize: 11
                        font.bold: sessionTabBar.currentIndex === 0
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                TabButton {
                    text: "Disk Usage"
                    font.pixelSize: 11
                    font.bold: sessionTabBar.currentIndex === 1
                    background: Rectangle {
                        implicitHeight: 32
                        color: sessionTabBar.currentIndex === 1 ? root.colorPrimary : "transparent"
                        border.color: root.colorBorder
                        border.width: sessionTabBar.currentIndex === 1 ? 0 : 1
                    }
                    contentItem: Text {
                        text: "Disk Usage"
                        color: sessionTabBar.currentIndex === 1 ? "#ffffff" : root.colorTextPrimary
                        font.pixelSize: 11
                        font.bold: sessionTabBar.currentIndex === 1
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            // Tab Content
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: sessionTabBar.currentIndex
                onCurrentIndexChanged: {
                    if (currentIndex === 1 && root.backend) {
                        root.backend.loadDiskUsage()
                        root.backend.loadBlockDevices()
                    }
                }

                FileExplorerView {
                    backend: root.backend
                    busy: root.backend ? root.backend.busy : false
                    onRequestNotice: (message) => {
                        root.requestNotice(message)
                    }
                    onRequestConfirm: (title, message, callback) => {
                        root.requestConfirm(title, message, callback)
                    }
                }

                DiskUsageView {
                    backend: root.backend
                    busy: root.backend ? root.backend.busy : false
                    onRequestNotice: (message) => {
                        root.requestNotice(message)
                    }
                }
            }

        }
    }

    // ------------------------------------------------------------------
    // Host Key Trust Dialog
    // ------------------------------------------------------------------
    Dialog {
        id: hostTrustDialog
        property string serverAddress: ""
        property string fingerprint: ""
        title: "Verify SSH Server Identity"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        width: 560

        contentItem: Column {
            width: 520
            spacing: 16
            anchors.margins: 16

            Rectangle {
                width: 48
                height: 48
                radius: 24
                color: root.colorWarning
                opacity: 0.12
                Text {
                    anchors.centerIn: parent
                    text: "⚠"
                    font.pixelSize: 24
                    color: root.colorWarning
                }
            }

            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "The SSH host key for " + hostTrustDialog.serverAddress
                    + " is not yet trusted.\n\nFingerprint (SHA256):\n"
                    + hostTrustDialog.fingerprint
                font.pixelSize: 13
                color: root.colorTextPrimary
            }

            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Only trust this server if you have verified this fingerprint "
                    + "with your server administrator using a separate, trusted method. "
                    + "Trusting it will save the key on this computer and reconnect."
                font.pixelSize: 12
                color: root.colorTextSecondary
            }
        }

        onAccepted: root.backend.acceptPendingHostKey()
        onRejected: root.backend.rejectPendingHostKey()
    }
}
