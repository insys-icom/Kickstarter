const top_topic = "kickstarter";
const text_disconnected = "Not online";
const text_connected = "Online";
var client;
var localfiles = {};
var fragments = [];
var profile = {};

var root = document.querySelector(':root');

// entry point: start MQTT web socket; the rest will be started by consuming received MQTT messages
function start_mqtt() {
    const host = "ws://" + window.location.hostname + ":9001";
    const clientId = 'ws_' + Math.random().toString().substring(2)
    const options = {
        keepalive: 30,
        clientId,
        protocolId: 'MQTT',
        protocolVersion: 5,
        clean: true,
        reconnectPeriod: 1000,
        connectTimeout: 30 * 1000,
        log: disable_mqtt_log,
        rejectUnauthorized: false
    }
    client = mqtt.connect(host, options)
    client.on('connect',   on_connect);
    client.on('reconnect', on_connect);
    client.on('error',     on_close);
    client.on('message',   on_message);
    client.on('close',     on_close);
}

// Disable all logging of MQTT client
function disable_mqtt_log () {;}

// MQTT got connected
function on_connect() {
    root.style.setProperty('--status_mqtt_broker_color', "green");
    document.getElementsByClassName("status_mqtt_broker")[0].innerHTML = text_connected;
    document.getElementById("rb_status").checked = true;

    client.subscribe(top_topic + '/#', { nl: true } ); // Do not listen to your own messages

    enable_elements(true);
}

// MQTT received message
function on_message(topic, message) {
    var mes = message.toString();

    if (topic == (top_topic + "/profile")) {
        profile = JSON.parse(mes);
        interprete_profile();
    }
    else if (topic == (top_topic + "/fw_latest")) { document.getElementById("fw_latest").innerHTML = mes; }
    else if (topic == (top_topic + "/log"))       { print_log(mes, "log_kickstarter"); }
    else if (topic == (top_topic + "/alert"))
    {
        if (mes.length > 1) {
            document.getElementById("alert").innerHTML = mes;
        }
        else {
            document.getElementById("alert").innerHTML = "";
        }
    }
    else if (topic == (top_topic + "/devices")) {
        const devices = JSON.parse(mes);
        let table = document.querySelector("#devicetable");
        table.innerHTML = "";
        if (devices.length > 0) {
            device_Table(table, devices);
            device_Table_Head(table, devices[0]);
        }
    }
    else if (topic == (top_topic + "/localfiles")) {
        for (var member in localfiles) delete localfiles[member];
        localfiles = JSON.parse(mes);
        display_stored_files();
        interprete_profile();
    }
    else if (topic == (top_topic + "/status")) {
        colour = "red";
        text = text_disconnected;
        if (mes == "online") {
            colour = "green";
            text = text_connected;
        }

        root.style.setProperty('--status_kickstarter_color', colour);
        var s = document.getElementsByClassName("status_kickstarter");
        for (var i = 0; i < s.length; i++) { s[i].innerHTML = text; };
    }
    else { console.log("received from unknown topic " + topic); }
}

// MQTT closed or errored
function on_close() {
    paint_offline();
    enable_elements(false);
}

// MQTT message should be sent
function send_message(msg, topic) {
    client.publish(topic, msg, { qos: 0, retain: false });
}

// display/hide boxes according to chosen menu
function view_boxes(menu) {
    var status_display = "none";
    var settings_display = "none";
    var files_display = "none";
    var help_display = "none";
    var help_index_display = "none";
    var upload_display = "none";
    var save_display = "none";

    var status_visibility = "hidden";
    var settings_visibility = "hidden";
    var files_visibility = "hidden";
    var help_visibility = "hidden";
    var help_index_visibility = "hidden";
    var upload_visibility = "hidden";
    var save_visibility = "hidden";

    switch (menu) {
        case "status":
            status_display = "block";

            status_visibility = "visible";
            break;

        case "settings":
            settings_display = "block";
            save_display = "block";

            settings_visibility = "visible";
            save_visibility = "visible";
            break;

        case "files":
            files_display = "block";
            upload_display = "block";

            files_visibility = "visible";
            upload_visibility = "visible";
            break;

        case "help":
            help_index_display = "block";
            help_display = "block";

            help_index_visibility = "visible";
            help_visibility = "visible";
            break;
    }

    root.style.setProperty('--box_status_display', status_display);
    root.style.setProperty('--box_status_visibility', status_visibility);

    root.style.setProperty('--box_settings_display', settings_display);
    root.style.setProperty('--box_settings_visibility', settings_visibility);

    root.style.setProperty('--box_files_display', files_display);
    root.style.setProperty('--box_files_visibility', files_visibility);

    root.style.setProperty('--box_help_index_display', help_index_display);
    root.style.setProperty('--box_help_index_visibility', help_index_visibility);
    root.style.setProperty('--box_help_display', help_display);
    root.style.setProperty('--box_help_visibility', help_visibility);

    root.style.setProperty('--box_upload_display', upload_display);
    root.style.setProperty('--box_upload_visibility', upload_visibility);

    root.style.setProperty('--box_save_display', save_display);
    root.style.setProperty('--box_save_visibility', save_visibility);

    help_chapter("overview.html");
}

// print head of table with detected devices
function device_Table_Head(table, json) {
    let thead = table.createTHead();
    let row = thead.insertRow();
    keys = Object.keys(json);
    for (key of keys) {
        let text = key
        if (key == "in_progress") {
            text = '';
        }
        let th = document.createElement("th");
        th.appendChild(document.createTextNode(text));
        row.appendChild(th);
    }
}

// print table with detected devices
function device_Table(table, json) {
    for (line of json) {
        let row = table.insertRow();
        keys = Object.keys(line);
        var i = 0;
        for (key of keys) {
            if (key == "in_progress") {
                if (line[key]) {
                    let img = document.createElement('img');
                    img.src = 'pics/spinner.gif';
                    img.style.width = '15px';
                    img.style.height = '15px';
                    img.style.margin = '0';
                    img.style.padding = '0';
                    row.insertCell().appendChild(img);
                }
                else {
                    row.insertCell().appendChild(document.createTextNode(''));
                }
            }
            else {
                var text = line[key]
                if (i == 3) {
                    var a = document.createElement('a');
                    // TODO: link zur klassischen UI wieder rausnehmen
                    a.innerHTML = '<a href="https://' + text + "/cgi_s_status" +
                                '" target="__new_window">' + text.substring(1, text.length - 1) +
                                '</a>';
                    row.insertCell().appendChild(a);
                }
                else {
                    row.insertCell().appendChild(document.createTextNode(text));
                }
                i++;
            }
        }
    }
}

// Paint everything as offline and in red colour
function paint_offline() {
    root.style.setProperty('--status_mqtt_broker_color', "red");
    var s = document.getElementsByClassName("status_mqtt_broker");
    for (var i = 0; i < s.length; i++) { s[i].innerHTML = text_disconnected; }

    root.style.setProperty('--status_kickstarter_color', "red");
    var s = document.getElementsByClassName("status_kickstarter");
    for (var i = 0; i < s.length; i++) { s[i].innerHTML = text_disconnected; }

    document.querySelector("#devicetable").innerHTML = "";
    document.querySelector("#filetable").innerHTML = "";
}

// print tail of log file
function print_log(message, logname) {
    maxlines = 35;
    log = document.getElementById(logname);
    logString = log.innerHTML
    log.innerHTML = "";
    if (logString.length > 0) {
        arr = logString.split('\n');
        var i = 0;
        if (arr.length > maxlines) {
            i = arr.length - maxlines;
        }
        for (; i < (arr.length - 1); i++) {
            var line = arr[i].substring(0, 140);
            line = line.replace(/[\r|\n|\r\n]$/, '');
            log.append(line);
            log.append('\n');
        }
    }
    log.append(message);
    log.append('\n');
}

// print table with all stored files
function display_stored_files() {
    let table = document.querySelector("#filetable");
    table.innerHTML = "";
    if (localfiles.length > 0) {
        for (line of localfiles) {
            let row = table.insertRow();
            keys = Object.keys(line);

            // print file name
            row.insertCell().appendChild(document.createTextNode(line[keys[0]]));

            // print file size
            row.insertCell().appendChild(document.createTextNode(line[keys[1]]));

            // print file modified date
            row.insertCell().appendChild(document.createTextNode(line[keys[2]]));

            // print sha256
            sha256 = line[keys[3]]
            let s = "---";
            if (sha256.length > 3) {
                s = sha256.substr(0, 6) + "...." + sha256.substr(sha256.length - 6, sha256.length);
            }
            row.insertCell().appendChild(document.createTextNode(s));
            row.lastChild.style = "cursor:pointer;";
            row.lastChild.title = sha256;

            // append delete icon (trash bin)
            let del = document.createElement("input");
            del.type = "image";
            del.className = "input_image";
            del.id = "del_file";
            del.src = "pics/trash.png";
            del.addEventListener('click', delete_file.bind(null, line[keys[0]]));
            row.insertCell().appendChild(del);

            // append download icon
            let dl = document.createElement("input");
            dl.type = "image";
            dl.className = "input_image";
            dl.id = "dl_file";
            dl.src = "pics/download.png";
            dl.addEventListener('click', download_file.bind(null, line[keys[0]]));
            row.insertCell().appendChild(dl);

            // remove item from fragment list, because it has been stored permanently
            var i = 0;
            while (i < fragments.length) {
                if (fragments[i].includes(line[keys[0]])) {
                    fragments.splice(i, 1);
                }
                else {
                    ++i;
                }
            }
            document.getElementById('files_uploading').innerHTML = fragments;
        }

        let thead = table.createTHead();
        let row = thead.insertRow();

        var th = document.createElement("th");
        th.appendChild(document.createTextNode("File name"));
        row.appendChild(th);

        var th = document.createElement("th");
        th.appendChild(document.createTextNode("File size"));
        row.appendChild(th);

        var th = document.createElement("th");
        th.appendChild(document.createTextNode("Last modified date"));
        row.appendChild(th);

        var th = document.createElement("th");
        th.appendChild(document.createTextNode("SHA256"));
        row.appendChild(th);
    }
}

// create a selector with all CSV files
function display_config_to_write() {
    var select = document.getElementById("config_to_write");
    var selected = "";

    // remove existing entries
    while (select.firstChild) {
        select.removeChild(select.lastChild);
    }
    selected_config = profile["config_table"]["filename"];

    // add "---" as none
    var opt = document.createElement('option');
    opt.innerHTML = opt.value = "---";
    if (selected_config === opt.value) {
        opt.selected = true;
    }
    select.appendChild(opt);

    // add all locally stored config files
    if (Object.keys(localfiles).length) {
        array = [];
        for (var i of localfiles) {
            // only accept files ending with .csv
            if ((i["name"].substr(i["name"].length - 4, i["name"].length)) == ".csv") {
                array.push(i["name"]);
            }
        }
        array.sort();
        for (var i = array.length - 1; i >= 0; i--) {
            var opt = document.createElement('option');
            opt.innerHTML = opt.value = array[i];
            if (selected_config === opt.value) {
                opt.selected = true;
                selected = opt.value;
            }
            select.appendChild(opt);
        }
    }
    // add download button
    var dl = document.getElementById("download_config");
    dl.hidden = true;
    if (selected.length) {
        if (selected.value != "---") {
            dl.hidden = false;
            dl.type = "image";
            dl.className = "input_image";
            dl.id = "download_config";
            dl.src = "pics/download.png";
            dl.addEventListener('click', download_file.bind(null, selected));
        }
    }
}

// create a selector with all firmware files
function display_firmware_to_write() {
    var select = document.getElementById("firmware_to_write");

    // remove existing entries
    while (select.firstChild) {
        select.removeChild(select.lastChild);
    }
    selected_firmware = profile["firmware"]["filename"];

    // add "---" as none
    var opt = document.createElement('option');
    opt.innerHTML = opt.value = "---";
    if (selected_firmware === opt.value) {
        opt.selected = true;
    }
    select.appendChild(opt);

    // add "latest" as a firmware
    var opt = document.createElement('option');
    opt.innerHTML = opt.value = "latest";
    if (selected_firmware === opt.value) {
        opt.selected = true;
    }
    select.appendChild(opt);

    // add all locally stored firmware files
    if (Object.keys(localfiles).length) {
        array = [];
        for (var i of localfiles) {
            // only accept full autoupdate files
            if (i["name"].startsWith("autoupdate-")) {
                if (i["name"].includes("-full.tar")) {
                    array.push(i["name"]);
                }
            }
        }
        array.sort();
        for (var i = array.length - 1; i >= 0; i--) {
            var opt = document.createElement('option');
            opt.innerHTML = opt.value = array[i];
            if (selected_firmware === opt.value) {
                opt.selected = true;
            }
            select.appendChild(opt);
        }
    }
}

// paint a table with all files except firmware files
function change_file_to_write(id, selected_filename) {
    var select = document.getElementById(id);
    var found_selected = false;

    // remove existing entries
    if (select) {
        while (select.firstChild) {
            select.removeChild(select.lastChild);
        }
    }

    // add all locally stored files except firmware
    if (localfiles) {
        array = [];
        for (var i of localfiles) {
            if (!i["name"].startsWith("autoupdate-")) {
                array.push(i["name"]);
            }
        }
        array.sort();
        for (var i = array.length - 1; i >= 0; i--) {
            var opt = document.createElement('option');
            opt.innerHTML = opt.value = array[i];
            if (selected_filename === opt.value) {
                opt.selected = true;
                found_selected = true;
            }
            select.appendChild(opt);
        }
    }

    // add an empty one
    var opt = document.createElement('option');
    opt.innerHTML = opt.value = "";
    if (!found_selected) {
        opt.selected = true;
    }
    select.appendChild(opt);
}

// read in a received profile and store it in global variables
function interprete_profile() {
    // do nothing if there is not yet known any profile
    if (!Object.hasOwn(profile, 'firmware')) {
        return;
    };

    display_firmware_to_write();
    display_config_to_write();
    display_upload();

    document.getElementById('check_active').checked = profile["auto-update"]["active"];
    document.getElementById('check_uri').value = profile["auto-update"]["uri"];
    document.getElementById('check_interval').value = Math.round(profile["auto-update"]["check_interval"]);

    document.getElementById('irm_active').checked = profile["irm"]["active"];
    document.getElementById('irm_uri').value = profile["irm"]["uri"];
    document.getElementById('irm_token').value = profile["irm"]["token"];
    document.getElementById('irm_group').value = profile["irm"]["group"];

    //document.getElementById('timezone_to_write').value = profile["time"]["timezone"];
}

// create "browse" and upload button
function filechooser(event) {
    var files = event.target.files;

    for (var i = 0, f; f = files[i]; i++) {
        // ignore huge files
        if (f.size > 40 * 1024 * 1024) {
            fragments.push('File too large, ignoring it: <strong>', f.name, '</strong> ', f.size, ' bytes', '<br>');
            continue;
        }
        var pic = '&nbsp;&nbsp;<img src="pics/spinner.gif" width=15px>'
        fragments.push('<strong>' + f.name + '</strong> ' + f.size + ' bytes' + pic + '<br>');

        // send file via MQTT after it has been selected
        var reader = new FileReader();
        reader.onloadend = (function(theFile) {
            return function(e) {
                var uploading = new Object();
                uploading.name = theFile.name;
                uploading.type = theFile.type;
                uploading.size = theFile.size;
                uploading.content = e.target.result;
                send_message(JSON.stringify(uploading), top_topic + "/upload");
            };
        })(f);

        reader.readAsDataURL(f);
    }

    // print list of uploading files
    document.getElementById('files_uploading').innerHTML = fragments.join('');
}

// print status "online" and green colour for everything that runs
function enable_elements(yesno) {
    var elements = [
        "store_settings"
    ];

    for (var i of elements) {
        document.getElementById(i).disabled = !yesno;
    }
}

// send MQTT message with profile to store
function store_settings() {
    //profile["time"]["timezone"] = document.getElementById('timezone_to_write').value;
    profile["firmware"]["filename"]     = document.getElementById('firmware_to_write').value;
    profile["config_table"]["filename"] = document.getElementById('config_to_write').value;

    profile["auto-update"]["active"]         = document.getElementById('check_active').checked;
    profile["auto-update"]["uri"]            = document.getElementById('check_uri').value;
    profile["auto-update"]["check_interval"] = document.getElementById('check_interval').value;

    profile["irm"]["active"]  = document.getElementById('irm_active').checked
    profile["irm"]["uri"]     = document.getElementById('irm_uri').value
    profile["irm"]["token"]   = document.getElementById('irm_token').value
    profile["irm"]["group"]   = document.getElementById('irm_group').value

    // get all the files that should be uploaded to the device
    var uploads = [];
    var table = document.getElementById("upload_table");
    var rows = table.querySelectorAll("tr");
    rows.forEach(function(row) {
        if (row.id.startsWith("del_upload_")) {
            var sel = row.cells[0].firstChild;
            var activate = row.cells[1].firstChild;
            uploads.push( { "filename": sel[sel.selectedIndex].text, "activate": activate.checked } );
        }
    });
    profile["uploads"] = uploads;

    send_message(JSON.stringify(profile), top_topic + "/profile_up");
}

// paint a table with all files that should be uploaded to the device
function display_upload() {
    let table = document.querySelector("#upload_table");
    table.setAttribute('class', 'list_table');
    table.innerHTML = "";

    // paint table header
    let thead = table.createTHead();
    let row = thead.insertRow();

    var th = document.createElement("th");
    th.appendChild(document.createTextNode("File name"));
    th.style = "text-align: left;";
    row.appendChild(th);

    var th = document.createElement("th");
    th.appendChild(document.createTextNode("activate ASCII"));
    row.appendChild(th);

    // paint all existing upload files
    if (Object.keys(localfiles).length) {
        for (entry of profile["uploads"]) {
            add_upload(entry, false);
        }
    }

    add_plus(table);
}

// add a table row containing a file, that should be uploaded to the device
function add_upload(entry, paint_add) {
    var table = document.getElementById("upload_table");

    // only insert a single new entry
    if (paint_add) {
        // delete last row that contains the plus icon
        table.deleteRow(table.rows.length -1);
    }

    // paint the id to get the complete upload deleted
    let row = table.insertRow();
    let rand_id = Math.random().toString().substring(2)
    row.id = "del_upload_" + rand_id;

    // first column: paint the selector with the files to upload
    let sel = document.createElement("select");
    sel.id = "file_to_write_" + rand_id;
    sel.name = sel.id;
    row.insertCell().appendChild(sel);
    if (selected_firmware) {
        change_file_to_write(sel.id, entry["filename"]);
    }

    // second column: paint the checkbox for activating detected ASCII files
    let activate = document.createElement("input");
    activate.type = "checkbox";
    activate.name = "activate_to_write_" + rand_id;
    activate.id = activate.name;
    if (entry["activate"]) {
        activate.checked = true;
    }
    row.insertCell().appendChild(activate);
    row.lastChild.style = "text-align: center;";

    // third column: paint delete button (trash bin icon)
    let del = document.createElement("input");
    del.type = "image";
    del.className = "input_image";
    del.src = "pics/trash.png";
    del.addEventListener('click', del_upload.bind(null, row.id));
    row.insertCell().appendChild(del);

    // fourth column: paint download button
    if (entry["filename"]) {
        if (entry["filename"].length) {
            let dl = document.createElement("input");
            dl.type = "image";
            dl.className = "input_image";
            dl.id = "dl_file";
            dl.src = "pics/download.png";
            dl.addEventListener('click', download_file.bind(null, entry["filename"]));
            row.insertCell().appendChild(dl);
        }
    }

    if (paint_add) {
        add_plus(table);
    }
}

// add a table row with only a plus button for new entries
function add_plus(table) {
    var row = table.insertRow();
    row.insertCell().appendChild(document.createTextNode(""));
    row.insertCell().appendChild(document.createTextNode(""));

    // paint add button (plus icon)
    let add = document.createElement("input");
    add.type = "image";
    add.className = "input_image";
    add.id = "add_upload";
    add.src = "pics/plus.png";
    add.addEventListener('click', add_upload.bind(null, "", true));
    row.insertCell().appendChild(add);
}

// delete a table row containing a file, that should be uploaded to the device
function del_upload(id) {
    var row = document.getElementById(id);
    row.parentNode.removeChild(row);
}

// send MQTT message to delete a file
function delete_file(filename) {
    let msg = { "filename": filename };
    send_message(JSON.stringify(msg), top_topic + "/delete_file");
}

// create an aritificial link for downloading a file
function download_file(filename) {
    var link = document.createElement('a');
    link.href = 'files/' + filename;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// print links to the help html sites
function help_chapter(chapter) {
    fetch("help/" + chapter)
        .then((res) => res.text())
        .then((text) => {
            document.getElementById("help_text").innerHTML = text;
        })
        .catch((e) => console.error(e));
}