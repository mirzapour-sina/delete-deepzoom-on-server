pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: window
    width: 1200
    height: 850
    minimumWidth: 900
    minimumHeight: 640
    visible: true
    title: "Remote DeepZoom Folder Cleaner"
    color: colorBg

    property var sessionManager: null
    property int activeSessionIndex: -1
    property var sessions: []
    property var sessionTabs: []  // session tab objects, kept in sync with sessionManager positions
    property bool showHiddenFilesDefault: false
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

    function showNotice(message) {
        toastNotification.show(message)
    }

    function showConfirm(title, message, callback) {
        confirmDialog.title = title
        confirmDialog.message = message
        confirmDialog.callback = callback
        confirmDialog.open()
    }

    // Non-blocking toast notification (replaces the blocking notice dialog)
    Rectangle {
        id: toastNotification
        width: 400
        height: 44
        color: "#333333"
        radius: 8
        opacity: 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 16
        z: 100

        Behavior on opacity {
            NumberAnimation { duration: 250 }
        }

        Text {
            anchors.centerIn: parent
            text: toastNotification.text
            color: "#ffffff"
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            width: 360
        }

        Timer {
            id: toastDismissTimer
            interval: 4000
            running: false
            repeat: false
            onTriggered: toastNotification.opacity = 0
        }

        property string text: ""

        function show(msg) {
            toastNotification.text = msg
            toastNotification.opacity = 1
            toastDismissTimer.start()
        }

        onOpacityChanged: {
            if (opacity === 0) toastDismissTimer.stop()
        }
    }

    // Generic Confirmation Dialog
    Dialog {
        id: confirmDialog
        property string confirmTitle: ""
        property string message: ""
        property var callback: null
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        width: 480
        title: confirmDialog.confirmTitle

        contentItem: Column {
            width: 440
            spacing: 16
            anchors.margins: 16

            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                text: confirmDialog.message
                font.pixelSize: 13
                color: window.colorTextPrimary
            }
        }

        onAccepted: {
            if (confirmDialog.callback) {
                confirmDialog.callback()
            }
        }
    }

    // Manage Connections Dialog
    Dialog {
        id: manageConnectionsDialog
        title: "Manage Saved Connections"
        modal: true
        standardButtons: Dialog.Close
        anchors.centerIn: parent
        width: 600
        height: 400

        ListView {
            id: historyList
            anchors.fill: parent
            anchors.margins: 12
            model: sessionManager ? sessionManager.connectionHistory : []
            spacing: 4
            clip: true

            delegate: Rectangle {
                required property var modelData
                width: parent.width
                height: 68
                radius: 8
                color: window.colorSurface
                border.color: window.colorBorder
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12

                    ColumnLayout { spacing: 2; Layout.fillWidth: true
                        Label {
                            text: modelData.host + ":" + modelData.port
                            font.pixelSize: 13
                            font.bold: true
                            color: window.colorTextPrimary
                        }
                        Label {
                            text: modelData.username + " @ " + modelData.remote_path
                            font.pixelSize: 11
                            color: window.colorTextSecondary
                        }
                        Label {
                            text: modelData.last_used ? "Last used: " + modelData.last_used.split("T")[0] : "Never used"
                            font.pixelSize: 10
                            color: window.colorTextMuted
                        }
                    }

                    Button {
                        text: "Load"
                        flat: true
                        onClicked: {
                            var profile = modelData
                            // Find the session and load the profile
                            // For now just close
                            manageConnectionsDialog.close()
                        }
                    }
                    Button {
                        text: "Remove"
                        flat: true
                        onClicked: {
                            window.sessionManager.removeConnection(
                                modelData.host, modelData.username, modelData.port, modelData.remote_path
                            )
                            manageConnectionsDialog.close()
                        }
                    }
                }
            }
        }
    }

    // Settings Dialog
    Dialog {
        id: settingsDialog
        title: "Settings"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        width: 500
        height: 300

        contentItem: Column {
            width: 460
            spacing: 16
            anchors.margins: 16

            Label {
                text: "Settings"
                font.pixelSize: 18
                font.bold: true
                color: window.colorTextPrimary
            }

            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Settings panel - placeholder for future options"
                font.pixelSize: 13
                color: window.colorTextSecondary
            }

            // Theme selector
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Label {
                    text: "Theme"
                    font.pixelSize: 12
                    color: window.colorTextSecondary
                    Layout.alignment: Qt.AlignLeft
                }

                ComboBox {
                    id: themeCombo
                    Layout.fillWidth: true
                    model: ["System", "Light", "Dark"]
                    currentIndex: window.theme === "dark" ? 2 : (window.theme === "light" ? 1 : 0)
                    onActivated: (idx) => {
                        var t = idx === 0 ? "system" : (idx === 1 ? "light" : "dark")
                        window.theme = t
                        var backend = window.sessionManager.getSessionBackend(0)
                        if (backend) {
                            backend.setTheme(t)
                        }
                    }
                    delegate: ItemDelegate {
                        required property var modelData
                        width: parent.width
                        text: modelData
                        font.pixelSize: 12
                        contentItem: Text {
                            text: modelData
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            CheckBox {
                text: "Save passwords in history"
                checked: false
                font.pixelSize: 13
            }

            CheckBox {
                text: "Show hidden files by default"
                checked: window.showHiddenFilesDefault
                font.pixelSize: 13
                onToggled: {
                    window.showHiddenFilesDefault = checked
                    var backend = window.sessionManager.getSessionBackend(0)
                    if (backend) {
                        backend.setShowHiddenFiles(checked)
                    }
                }
            }
        }
    }

    ColumnLayout {
        objectName: "mainColumnLayout"
        width: window.width
        height: window.height
        spacing: 0

        // Main Session Tab Bar
        Rectangle {
            id: sessionTabBarContainer
            Layout.fillWidth: true
            height: 36
            color: window.colorSurface
            border.color: window.colorBorder
            border.width: 1

            TabBar {
                id: sessionTabBar
                anchors.fill: parent
                contentHeight: 36

                // Session tabs will be added dynamically via Repeater
                Repeater {
                    model: window.sessions
                    delegate: TabButton {
                        id: sessionTabButton
                        required property int index
                        required property var modelData

                        readonly property int sessionIndex: index
                        readonly property bool isConnected: modelData.connected
                        readonly property string host: modelData.host
                        readonly property int port: modelData.port

                        font.pixelSize: 11
                        font.bold: sessionTabBar.currentIndex === index

                        background: Rectangle {
                            implicitHeight: 36
                            color: sessionTabBar.currentIndex === index ? window.colorPrimary : window.colorSurfaceHover
                            border.color: window.colorBorder
                            border.width: sessionTabBar.currentIndex === index ? 0 : 1
                        }

                        // Custom tab content with close button
                        contentItem: Item {
                            id: tabContent
                            implicitWidth: 130
                            implicitHeight: 36

                            Text {
                                id: tabText
                                anchors.left: parent.left
                                anchors.right: closeBtn.left
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 12
                                anchors.rightMargin: 4
                                text: modelData.host
                                    ? (modelData.connected ? "● " : "○ ") + modelData.host + ":" + modelData.port
                                    : ("Session " + modelData.id)
                                color: sessionTabBar.currentIndex === index ? "#ffffff" : window.colorTextSecondary
                                font.pixelSize: 11
                                font.bold: sessionTabBar.currentIndex === index
                                elide: Text.ElideRight
                            }

                            // Connection status dot
                            Rectangle {
                                id: statusDot
                                anchors.left: tabText.left
                                anchors.top: parent.top
                                anchors.topMargin: 7
                                width: 6
                                height: 6
                                radius: 3
                                visible: sessionTabButton.isConnected
                                color: window.colorSuccess
                            }

                            // Close button - right aligned, appears on hover
                            Rectangle {
                                id: closeBtn
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                width: 18
                                height: 18
                                radius: 9
                                color: closeHover.hovered ? window.colorDanger : "transparent"

                                visible: closeHover.hovered || sessionTabBar.currentIndex === index

                                Behavior on color { ColorAnimation { duration: 120 } }
                                Behavior on visible { NumberAnimation { duration: 120 } }

                                Text {
                                    anchors.centerIn: parent
                                    text: "✕"
                                    color: closeHover.hovered ? "#ffffff" : window.colorTextMuted
                                    font.pixelSize: 10
                                    font.bold: true
                                }

                                MouseArea {
                                    id: closeHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        window.sessionManager.removeSession(sessionTabButton.sessionIndex)
                                        window.activeSessionIndex = window.sessionManager.getActiveSessionIndex()
                                    }
                                }

                                ToolTip.visible: closeHover.containsMouse
                                ToolTip.delay: 600
                                ToolTip.text: "Close session"
                            }
                        }

                        onClicked: {
                            window.sessionManager.setActiveSession(sessionIndex)
                            window.activeSessionIndex = sessionIndex
                        }
                    }
                }

                // Add Session Button (always at the end)
                TabButton {
                    text: "+"
                    font.pixelSize: 14
                    font.bold: true
                    width: 36
                    onClicked: {
                        var newIndex = window.sessionManager.addSession()
                        window.sessionManager.setActiveSession(newIndex)
                        window.activeSessionIndex = newIndex
                    }
                }
            }
        }

        // Session Content Area
        Item {
            id: sessionStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: true

            // Session tabs are children; visibility is managed by activeSessionIndex
            // (see activeSessionChanged handler below). ColumnLayout only sizes
            // QQuickItem children, so StackLayout (a Layout, not an Item) would
            // collapse to 0x0 here and show a blank page.
        }

        // Welcome Screen (MobaXterm-style) - shown when no sessions exist
        Item {
            id: welcomeScreen
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: false

            Column {
                anchors.centerIn: parent
                spacing: 24

                // App Logo/Title
                Column {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 12

                    Rectangle {
                        width: 96
                        height: 96
                        radius: 48
                        color: window.colorPrimary
                        Text {
                            anchors.centerIn: parent
                            text: "📁"
                            font.pixelSize: 48
                        }
                    }

                    Label {
                        text: "Remote DeepZoom Cleaner"
                        font.pixelSize: 28
                        font.bold: true
                        color: window.colorTextPrimary
                    }

                    Label {
                        width: 500
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        text: "Manage DeepZoom folders on Linux servers via SSH. Create sessions to connect to multiple servers simultaneously."
                        font.pixelSize: 14
                        color: window.colorTextSecondary
                    }
                }

                Rectangle {
                    width: 400
                    height: 1
                    color: window.colorBorder
                }

                // Quick Actions
                Column {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 12

                    Button {
                        text: "New Session"
                        font.pixelSize: 14
                        font.bold: true
                        height: 48
                        width: 300
                        background: Rectangle {
                            implicitHeight: 48
                            radius: 10
                            color: window.colorPrimary
                            border.color: window.colorPrimary
                            border.width: 1
                        }
                        contentItem: Text {
                            text: "New Session"
                            color: "#ffffff"
                            font.pixelSize: 14
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: {
                            var newIndex = window.sessionManager.addSession()
                            window.sessionManager.setActiveSession(newIndex)
                            window.activeSessionIndex = newIndex
                        }
                    }

                    Button {
                        text: "Load Saved Connection"
                        font.pixelSize: 13
                        height: 44
                        width: 300
                        flat: true
                        background: Rectangle {
                            implicitHeight: 44
                            radius: 10
                            color: window.colorSurface
                            border.color: window.colorBorder
                            border.width: 1
                        }
                        contentItem: Text {
                            text: "Load Saved Connection"
                            color: window.colorPrimary
                            font.pixelSize: 13
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: {
                            // Open manage connections to pick from history
                            manageConnectionsDialog.open()
                        }
                    }

                    Button {
                        text: "Settings"
                        font.pixelSize: 13
                        height: 44
                        width: 300
                        flat: true
                        background: Rectangle {
                            implicitHeight: 44
                            radius: 10
                            color: window.colorSurface
                            border.color: window.colorBorder
                            border.width: 1
                        }
                        contentItem: Text {
                            text: "Settings"
                            color: window.colorTextSecondary
                            font.pixelSize: 13
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: {
                            settingsDialog.open()
                        }
                    }
                }

                // Recent Sessions (if any)
                Item {
                    id: recentSessions
                    visible: sessionManager && sessionManager.connectionHistory.length > 0
                    width: 500

                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 8

                        Label {
                            text: "Recent Connections"
                            font.pixelSize: 13
                            font.bold: true
                            color: window.colorTextPrimary
                        }

                        ListView {
                            width: 500
                            height: 200
                            clip: true
                            model: sessionManager ? sessionManager.connectionHistory : []
                            spacing: 4

                            delegate: Rectangle {
                                required property var modelData
                                width: parent.width
                                height: 56
                                radius: 8
                                color: window.colorSurface
                                border.color: window.colorBorder
                                border.width: 1

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 12

                                    Rectangle {
                                        width: 40
                                        height: 40
                                        radius: 8
                                        color: window.colorPrimaryLight
                                        Text {
                                            anchors.centerIn: parent
                                            text: "🖥"
                                            font.pixelSize: 20
                                        }
                                    }

                                    ColumnLayout { spacing: 2; Layout.fillWidth: true
                                        Label {
                                            text: modelData.host + ":" + modelData.port
                                            font.pixelSize: 13
                                            font.bold: true
                                            color: window.colorTextPrimary
                                        }
                                        Label {
                                            text: modelData.username + " @ " + modelData.remote_path
                                            font.pixelSize: 11
                                            color: window.colorTextSecondary
                                        }
                                        Label {
                                            text: modelData.last_used ? "Last used: " + modelData.last_used.split("T")[0] : "Never used"
                                            font.pixelSize: 10
                                            color: window.colorTextMuted
                                        }
                                    }

                                    Button {
                                        text: "Connect"
                                        flat: true
                                        font.pixelSize: 12
                                        onClicked: {
                                            // Create session and connect
                                            var newIndex = window.sessionManager.addSession()
                                            window.sessionManager.setActiveSession(newIndex)
                                            window.activeSessionIndex = newIndex
                                            // The SessionTab will load the history when its dialog opens
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

    }

    // Initialize sessions on startup
    Component.onCompleted: {
        if (window.sessionManager) {
            // Connect signals FIRST so no session is missed
            window.sessionManager.sessionAdded.connect(function(index) {
                createSessionTab(index)
                refreshSessions()
            })

            window.sessionManager.sessionRemoved.connect(function(index) {
                var tab = window.sessionTabs[index]
                if (tab) {
                    tab.destroy()
                }
                window.sessionTabs.splice(index, 1)
                var count = window.sessionManager.getSessionCount()
                if (window.activeSessionIndex >= count) {
                    window.activeSessionIndex = count - 1
                }
                refreshSessions()
            })

            window.sessionManager.sessionUpdated.connect(function(index) {
                refreshSessions()
            })

            window.sessionManager.activeSessionChanged.connect(function(index) {
                window.activeSessionIndex = index
                sessionTabBar.currentIndex = index
                // Show only the active session tab; hide the rest
                for (var i = 0; i < window.sessionTabs.length; i++) {
                    var tab = window.sessionTabs[i]
                    if (tab) tab.visible = (i === index)
                }
            })

            // Create tabs for sessions that already exist (added before QML loaded)
            var existingCount = window.sessionManager.getSessionCount()
            for (var i = 0; i < existingCount; i++) {
                createSessionTab(i)
            }

            refreshSessions()

            // Load connection history from first session's backend
            var firstBackend = window.sessionManager.getSessionBackend(0)
            if (firstBackend) {
                firstBackend.loadConnectionHistory()
                window.showHiddenFilesDefault = firstBackend.showHiddenFiles()
                // Apply the saved UI theme to the window.
                // Light theme is the default for now; "system" resolves to light.
                // Dark mode will be brought back with a full dark-theme pass.
                var savedTheme = firstBackend.getTheme()
                window.theme = (savedTheme === "dark") ? "dark" : "light"
            }

            window.activeSessionIndex = window.sessionManager.getActiveSessionIndex()
            sessionTabBar.currentIndex = window.activeSessionIndex
            // Ensure the active session tab is visible on startup
            for (var i = 0; i < window.sessionTabs.length; i++) {
                var tab = window.sessionTabs[i]
                if (tab) tab.visible = (i === window.activeSessionIndex)
            }
        }
    }

    function refreshSessions() {
        var newSessions = window.sessionManager.getAllSessions()
        window.sessions = newSessions
    }

    function createSessionTab(index) {
        var component = Qt.createComponent("SessionTab.qml")
        if (component.status === Component.Ready) {
            var backend = window.sessionManager.getSessionBackend(index)
            var sessionInfo = window.sessionManager.getSessionInfo(index)

            var sessionTab = component.createObject(sessionStack, {
                "backend": backend,
                "sessionIndex": index,
                "sessionName": sessionInfo.name || ("Session " + sessionInfo.id),
                "host": sessionInfo.host || "",
                "port": sessionInfo.port || 22,
                "username": sessionInfo.username || "",
                "visible": false
            })

            // Connect session tab signals to handlers
            if (sessionTab) {
                window.sessionTabs.push(sessionTab)
                sessionTab.requestNotice.connect(showNotice)
                sessionTab.requestConfirm.connect(showConfirm)
                sessionTab.requestConnect.connect(function() {
                    // This will be handled by SessionTab's internal connection form
                })
                sessionTab.manageConnectionsRequested.connect(function() {
                    window.manageConnectionsDialog.open()
                })

                sessionTab.sessionConnectionStatusChanged.connect(function(status, message) {
                    // Update session info in manager
                    if (status === "connected") {
                        window.sessionManager.setSessionConnected(index, true)
                        window.sessionManager.updateSessionInfo(index,
                            sessionTab.host + ":" + sessionTab.port,
                            sessionTab.host,
                            sessionTab.port,
                            sessionTab.username
                        )
                        window.sessionManager.reloadConnectionHistory()
                    } else {
                        window.sessionManager.setSessionConnected(index, false)
                    }
                })
            }
        } else if (component.status === Component.Error) {
            console.error("Failed to load SessionTab:", component.errorString())
        }
    }
}