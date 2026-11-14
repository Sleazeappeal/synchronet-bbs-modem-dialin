// Part of the 40-column PETSCII screens, GPL-2.0-or-later (see NOTICE.txt).
// mods/logon.js: narrow (40-column PETSCII) callers get shorter
// text strings for this session only; everyone then runs the stock
// exec/logon.js unchanged.
if (console.screen_columns < 80) {
	var narrow = {
		// New-message scan: one line per sub-board
		NScanStatusFmt: "\x01-\r\n\x01y\x01h%.0s%-22.22s \x01n\x01cNew:\x01h%4u\x01n\x01c/\x01h%-u",
		// System information (Main Info: I), 10-column labels
		SiSysName: "\x01b\x01hSystem  : \x01c%s\r\n",
		SiSysID: "\x01bQWK ID  : \x01c%s\r\n",
		SiSysFaddr: "\x01bFidoNet : \x01c%s\r\n",
		SiSysPsite: "\x01bPostLink: \x01c%s %u\r\n",
		SiSysLocation: "\x01bLocation: \x01c%s\r\n",
		SiSysop: "\x01bOperator: \x01c%s\r\n",
		SiSysNodes: "\x01bNodes   : \x01c%u\r\n",
		SiNodeNumberName: "\x01bNode \x01c%-3d\x01b: \x01c%s\r\n",
		SiNodePhone: "\x01bPhone   : \x01c%s\r\n",
		SiTotalLogons: "\x01bLogons  : \x01c%s\r\n",
		SiLogonsToday: "\x01b today  : \x01c%s\r\n",
		SiTotalTime: "\x01bTime    : \x01c%s min\r\n",
		SiTimeToday: "\x01b today  : \x01c%s min\r\n",
		// Local time: date and time zone on separate lines
		TiNow: "\x01bNow     : \x01c%s\r\n          %s\r\n"
	};
	for (var id in narrow) {
		if (bbs.text[id] !== undefined)	// skip ids an older Synchronet lacks
			bbs.replace_text(bbs.text[id], narrow[id]);
	}
}
load(system.exec_dir + "logon.js");
