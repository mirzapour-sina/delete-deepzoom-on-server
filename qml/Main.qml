pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: window
    width: 920
    height: 720
    minimumWidth: 680
    minimumHeight: 540
    visible: true
    title: "Remote DeepZoom Folder Cleaner"
    color: "#f4f6fa"

    property bool busy: false
    property var backend: null

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

    ListModel {
        id: folderModel
    }

    Connections {
        target: window.backend

        function onBusyChanged(value) {
            window.busy = value
        }

        function onErrorOccurred(message) {
            errorDialog.text = message
            errorDialog.open()
        }

        function onStatusChanged(message) {
            statusLabel.text = message
        }

        function onFoldersLoaded(folders) {
            folderModel.clear()
            for (let i = 0; i < folders.length; ++i) {
                folderModel.append({
                    name: folders[i].name,
                    path: folders[i].path,
                    selected: false
                })
            }
        }

        function onFoldersRemoved(paths) {
            for (let i = folderModel.count - 1; i >= 0; --i) {
                if (paths.indexOf(folderModel.get(i).path) !== -1)
                    folderModel.remove(i)
            }
        }

        function onHostKeyTrustRequested(host, port, fingerprint) {
            hostTrustDialog.serverAddress = host + ":" + port
            hostTrustDialog.fingerprint = fingerprint
            hostTrustDialog.open()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        Label {
            text: "Remote DeepZoom Folder Cleaner"
            font.pixelSize: 24
            font.bold: true
            color: "#1e293b"
        }

        Label {
            text: "Connect over SSH, choose folders, then remove them on the Linux server."
            color: "#475569"
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        GridLayout {
            columns: 5
            columnSpacing: 10
            rowSpacing: 8
            Layout.fillWidth: true

            Label { text: "Server" }
            TextField {
                id: hostField
                placeholderText: "host or IP address"
                Layout.fillWidth: true
                Layout.columnSpan: 2
            }
            Label { text: "Port" }
            TextField {
                id: portField
                text: "22"
                inputMethodHints: Qt.ImhDigitsOnly
                Layout.preferredWidth: 90
            }

            Label { text: "Username" }
            TextField {
                id: usernameField
                placeholderText: "Linux username"
                Layout.fillWidth: true
                Layout.columnSpan: 4
            }

            Label { text: "Remote parent path" }
            TextField {
                id: pathField
                placeholderText: "/data/deepzoom"
                Layout.fillWidth: true
                Layout.columnSpan: 4
                onAccepted: connectButton.clicked()
            }

            Label { text: "SSH key file" }
            TextField {
                id: keyField
                placeholderText: "Optional; otherwise use SSH agent/default key"
                Layout.fillWidth: true
                Layout.columnSpan: 4
            }

            Label { text: "Password" }
            TextField {
                id: passwordField
                placeholderText: "Optional; leave blank for key/agent authentication"
                echoMode: TextInput.Password
                Layout.fillWidth: true
                Layout.columnSpan: 4
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Button {
                id: connectButton
                text: window.busy ? "Please wait…" : "Connect and load folders"
                enabled: !window.busy
                onClicked: window.backend.connectAndLoad(
                    hostField.text,
                    usernameField.text,
                    portField.text,
                    pathField.text,
                    keyField.text,
                    passwordField.text
                )
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Select all"
                enabled: !window.busy && folderModel.count > 0
                onClicked: window.setAllSelected(true)
            }
            Button {
                text: "Select none"
                enabled: !window.busy && folderModel.count > 0
                onClicked: window.setAllSelected(false)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "white"
            border.color: "#d8dee9"
            radius: 6

            ScrollView {
                anchors.fill: parent
                anchors.margins: 8
                clip: true

                Column {
                    width: parent.width
                    spacing: 2

                    Repeater {
                        model: folderModel
                        delegate: RowLayout {
                            id: folderRow
                            required property string name
                            required property string path
                            required property bool selected
                            required property int index
                            width: parent.width
                            spacing: 8

                            CheckBox {
                                checked: folderRow.selected
                                enabled: !window.busy
                                onToggled: folderModel.setProperty(folderRow.index, "selected", checked)
                            }

                            Label {
                                text: folderRow.path
                                color: "#0f172a"
                                wrapMode: Text.WrapAnywhere
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                    }

                    Label {
                        visible: folderModel.count === 0
                        width: parent.width
                        padding: 12
                        text: "No folders loaded. Connect to a server to browse."
                        color: "#64748b"
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Label {
                id: statusLabel
                text: "Ready."
                color: "#475569"
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Button {
                text: "Remove selected"
                enabled: !window.busy && window.selectedPaths().length > 0
                highlighted: true
                onClicked: confirmationDialog.open()
            }
        }
    }

    Dialog {
        id: hostTrustDialog
        property string serverAddress: ""
        property string fingerprint: ""
        title: "Verify SSH server identity"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        width: Math.min(window.width - 40, 620)

        contentItem: Label {
            width: hostTrustDialog.width
                - hostTrustDialog.leftPadding - hostTrustDialog.rightPadding
            wrapMode: Text.WordWrap
            text: "The SSH host key for " + hostTrustDialog.serverAddress
                + " is not yet trusted.\n\nFingerprint:\n"
                + hostTrustDialog.fingerprint
                + "\n\nOnly trust this server if you have verified this fingerprint "
                + "with your server administrator using a separate, trusted method. "
                + "Trusting it will save the key on this computer and reconnect."
        }

        onAccepted: window.backend.acceptPendingHostKey()
        onRejected: window.backend.rejectPendingHostKey()
    }

    Dialog {
        id: confirmationDialog
        title: "Confirm permanent deletion"
        modal: true
        standardButtons: Dialog.Yes | Dialog.Cancel
        anchors.centerIn: parent
        width: Math.min(window.width - 40, 540)

        contentItem: Label {
            width: confirmationDialog.width
                - confirmationDialog.leftPadding - confirmationDialog.rightPadding
            wrapMode: Text.WordWrap
            text: "Permanently delete " + window.selectedPaths().length
                + " selected folder(s) from the Linux server? This cannot be undone."
        }

        onAccepted: window.backend.removeFolders(window.selectedPaths())
    }

    Dialog {
        id: errorDialog
        property string text: ""
        title: "Operation notice"
        modal: true
        standardButtons: Dialog.Ok
        anchors.centerIn: parent
        width: Math.min(window.width - 40, 660)

        contentItem: Label {
            width: errorDialog.width - errorDialog.leftPadding - errorDialog.rightPadding
            wrapMode: Text.WrapAnywhere
            text: errorDialog.text
        }
    }
}
