var ck_timeout;

function login_toggle_pass()
{
	if(document.getElementById('login_password').type == 'password')
		document.getElementById('login_password').type = 'text';
	else
		document.getElementById('login_password').type = 'password';
}

function submit_login()
{
	amp_event('Login Start');
	if (!$('#login_email').val())
	{
		$('#login_email').effect('highlight', 1000);
		$('#login_email').focus();
		return false;
	}
	if (!$('#login_password').val())
	{
		$('#login_password').effect('highlight', 1000);
		$('#login_password').focus();
		return false;
	}
	$('#log_in').attr('disabled', true);
	$.ajax({
		type: 'POST',
		url: '/ajax/user_login',
		data:   { email: $('#login_email').val(), password: $('#login_password').val(), kmli: $('#kmli').prop('checked') ? 1 : 0, captcha_data: captcha_data, key: xsrf_key },
		success: function(response)
		{
			amp_event('Login Complete');
			location.reload(true);
		},
		error: function (xhr)
     	{
     		$('#log_in').attr('disabled', false);
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
     		if(message.code==1)
     			show_login();
  		}

	});
	
}


function show_signup(from)
{
	if($(document).width() < 500)
		var box_width = "98%";
	else
		var box_width = "400px";
	$.ajax({
		type: 'GET',
        url: '/ajax/user_signup?from=' + from + '&uri=' + window.location,
        success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#site_dialog').dialog('close');$('body').removeClass('modal_active');});$('body').addClass('modal_active');}, close: function(){$('body').removeClass('modal_active');} });
        }

    });
    return false;
}

function show_login()
{
	if($(document).width() < 500)
		var box_width = "98%";
	else
		var box_width = "30%";
	$.ajax({
		type: 'GET',
        url: '/ajax/show_user_login?uri=' + window.location,
        success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#site_dialog').dialog('close');$('body').removeClass('modal_active');});$('body').addClass('modal_active');}, close: function(){$('body').removeClass('modal_active');} });
        }

    });
    return false;
}


function show_topic_flair(bid,tid,mid)
{
	if($(document).width() < 500)
		var box_width = "75%";
	else
		var box_width = "35%";
	$('.flair_dialog').dialog({ resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('.flair_dialog').dialog('close');});} });
	return false;
}

function show_pm_dialog()
{
	$('.pm_dialog input[name="subject"]').val('');
	$('.pm_dialog textarea[name="message"]').val('');

	if($(document).width() < 500)
		var box_width = "75%";
	else
		var box_width = "35%";
	$('.pm_dialog').dialog({ resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('.pm_dialog').dialog('close');});} });
	return false;
}


function track_event(event_id)
{
	if(typeof(om)==='object')
	{
		om.trackEvent(event_id);
		return true;
	}
	if(typeof somni=='undefined')
		return true;
	somni.linkTrackVars=null;
	somni.linkTrackEvents=somni.events="event" + event_id;
	var s_code = somni.tl(this,'o','eventTrack');
	if(s_code)document.write(s_code);
	return true;
}

function pm_click(url, key, user_name)
{
	var newForm = $('<form>', {
		'action': url,
		'method': 'post'
	});
	newForm.append($('<input>', {
		'name': 'key',
		'value': key,
		'type': 'hidden'
	}));
	newForm.append($('<input>', {
		'name': 'to',
		'value': user_name,
		'type': 'hidden'
	}));
	newForm.appendTo( document.body );
    newForm.submit();
}

function clear_all_notifications()
{
	$.ajax({
		type: 'GET',
        url: '/ajax/notification_clear_all',
        success: function(response)
		{
			if(response=='')
			{
				$('#ndrop_span').html('<a class="top_user_icon" href="/user/notifications"><i class="fa fa-bell-o dim" title="No Unread Notifications"></i></a>');
			}
        }
    });
	return false;
}

function clear_all_badge_notifications(user_name)
{
	$.ajax({
		type: 'GET',
        url: '/ajax/badge_notification_clear_all',
        success: function(response)
		{
			if(response=='')
			{
				$('#bndrop_span').html('<a class="top_user_icon" href="/community/'+user_name+'/badges"><i class="fa fa-trophy dim" title="No New Badges"></i></a>');
			}
        }
    });
	return false;
}

function topnav_side_open()
{
	$("#sidenav").addClass("sidenav_open");
	$(".wrapper").append('<div id="fso" class="fs_overlay"></div>');
	$("#fso").click(function() { topnav_side_close();});
}

function topnav_side_close()
{
	$("#sidenav").removeClass("sidenav_open");
	$("#fso").remove();
}

function topnav_show_search()
{
	$('.masthead_search').toggle();
	$('#searchtextbox').focus();
}

function topnav_hide_search()
{
	$('.masthead_search').toggle();
	$('#searchtextbox').val('');
}

function count_chars_uc(field_id, field_name, max_chars, allow_unicode, warning_id)
{
	var check = $('#' + field_id).val().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
	var cnt = check.length;
	if(cnt > max_chars)
	{
		$('#' + warning_id).html('Error: ' + field_name + ' submissions cannot be longer than ' + max_chars + ' characters (currently ' + cnt + ')');
	}
	else if(cnt > (max_chars * 0.8))
	{
		$('#' + warning_id).html('Warning: ' + (max_chars - cnt) + ' characters remaining (maximum ' + max_chars + ')');
	}
	else if(!allow_unicode)
	{
		if($('#' + field_id).val().match(/[\u0100-\u2017\u201E-\uffff]/))
		{
			$('#' + warning_id).html('Warning: Unicode characters are automatically removed from ' + field_name + ' submissions');
		}
	}
	else
	{
		$('#' + warning_id).html('');
	}
}

function ad_report()
{
	var dbg = 'No data available';
	if (storageAvailable('localStorage'))
		if(localStorage.getItem("revdbg")!=null)
			dbg=localStorage.getItem("revdbg");
	var newForm = $('<form>', {
		'action': '/feedback?type=62',
		'method': 'post'
	});
	newForm.append($('<input>', {
		'name': 'pre_message',
		'value': dbg,
		'type': 'hidden'
	}));
	newForm.appendTo( document.body );
	newForm.submit();
}

function toggle_qna_notify(product, question)
{
	$.ajax({
		type: 'POST',
        url: '/ajax/qna_notify',
        data: { p: product, q: question, key: xsrf_key },
        success: function(response)
		{
			if(question)
			{
				if(response==1)
				{
					$('#text_qna_notify').hide().html('You are now tracking this Question').fadeIn(250);
					$('#btn_qna_notify').hide().html('Stop Tracking').fadeIn(250);
				}
				else
				{
					$('#text_qna_notify').hide().html('Let me know when there are new Answers for this Question:').fadeIn(250);
					$('#btn_qna_notify').hide().html('Notify Me').fadeIn(250);
				}
			}
			else
			{
				if(response==1)
				{
					$('#btn_qna_notify').hide().html('&#x2714; Tracking Questions').fadeIn(250);
					$('#qna_track i').addClass('fa-bell').removeClass('fa-bell-o');
				}
				else
				{
					$('#btn_qna_notify').hide().html('Track New Questions').fadeIn(250);
					$('#qna_track i').addClass('fa-bell-o').removeClass('fa-bell');
				}
				if($('#gs_noty i').hasClass('fa-bell'))
					$('.gs_hb_notify i').addClass('fa-bell').removeClass('fa-bell-o');
				else
					$('.gs_hb_notify i').addClass('fa-bell-o').removeClass('fa-bell');

			}
        }
    });
	return false;
}

function escape_html(data)
{
    return data.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function storageAvailable(type)
{
	try  { var storage = window[type], x = '__storage_test__'; storage.setItem(x, x); storage.removeItem(x); return true; } catch(e) {return e instanceof DOMException && (e.code === 22 || e.code === 1014 || e.name === 'QuotaExceededError' || e.name === 'NS_ERROR_DOM_QUOTA_REACHED') && storage.length !== 0; }
}

function revdbg(e)
{
	if(!e.isEmpty)
	{
		if (storageAvailable('localStorage'))
		{
			var maxPages = 20;
			var dbg = [];
			if(localStorage.getItem("revdbg")!=null) dbg=JSON.parse(localStorage.getItem("revdbg"));
			var adsList=[]; var thisPage=[];
			while(dbg.length>maxPages) dbg.shift();
			if(dbg.length) { if(dbg[dbg.length-1]["v"]==vguid) { thisPage=dbg.pop(); adsList=thisPage.al; }}
			var adinfo=new Object(); adinfo.a=e.advertiserId; adinfo.ca=e.campaignId; adinfo.cr=e.creativeId; adinfo.l=e.lineItemId; adinfo.s=e.size; adinfo.sac=e.sourceAgnosticCreativeId; adinfo.sal=e.sourceAgnosticLineItemId;
			adsList.push(adinfo); dbg.push({"v": vguid, "u":location.pathname, "t":new Date(), "al":adsList});
			//console.log(JSON.stringify(dbg));
			localStorage.setItem("revdbg",JSON.stringify(dbg));
		}
	}
}

function qna_show_edit_module(pid, qid, xsrf_key)
{
	if($(document).width() < 750)
		var box_width = "95%";
	else
		var box_width = "60%";
	$.ajax({
		type: 'POST',
		url: '/ajax/qna_edit_dialog',
		data: {pid: pid, qid: qid, key: xsrf_key},
		success: function(response)
		{
			if(response.error)
				alert(response.error.replace(/&quot;/g, '"'));
			else
			{
				$('#site_dialog').html(response);
				$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true });
			}
		}

	});
    return false;
}

function qna_post_question_edit(pid, qid)
{
	if($('.flair_select .flair.current'))
		category = $('.flair_select .flair.current').attr('data-id');
	else
		category = 1;
	var question_edit = $("#question.qedit").val().trim();
	if($("#spoiler.qedit").prop('checked'))
		var spoiler_edit = 1;
	else
		var spoiler_edit = 0;
	var details_edit = $("#details.qedit").val().trim();

	$.ajax({
		type: 'POST',
		url: '/ajax/qna_edit_dialog?update=1',
		data: {pid: pid, qid: qid, title: question_edit, cat: category, message: details_edit, spoiler: spoiler_edit, key: xsrf_key},
		success: function(response)
		{
			if(response.error)
				alert(response.error);
			else
			{
				alert('Question has been successfully edited.');
				location.reload(true);
			}
		}
	});

	return;
}

function recaptcha_success(response)
{
	captcha_good = true;
	captcha_data = response;
	$("#log_in").prop("disabled", false);
	reg_ready_check();
}

function recaptcha_expired(response)
{
	captcha_good = false;
	captcha_data = '';
	reg_ready_check();
}

function reg_toggle_pass()
{
	if(document.getElementById('password').type == 'password')
		document.getElementById('password').type = 'text';
	else
		document.getElementById('password').type = 'password';
}

function reg_user_name_check()
{
	$('#reg_create').attr('disabled', true);
	var error = '';
	var name_check = $('#user_name').val();
	if(name_check.length < 1)
	{
		$('#name_icon').removeClass();
		$('#name_error').html('');
	}
	else if(error =username_validate(name_check))
	{
		$('#name_error').html(error);
		$('#name_icon').removeClass().addClass('fa reg_invalid fa-remove');
	}
	else
	{
		$('#name_icon').removeClass().addClass('fa fa-pulse fa-spinner');
		if(ck_timeout)
			clearTimeout(ck_timeout);
		ck_timeout = setTimeout(reg_user_name_full_check, 500);
	}
}

function reg_user_name_full_check()
{
	$.ajax({
		type: 'POST',
		url: '/ajax/username_check',
		data:  { name: $('#user_name').val(), key: xsrf_key },
		success: function(response)
		{
			if(response)
			{
				$('#name_icon').removeClass().addClass('fa reg_invalid fa-remove');
				$('#name_error').html(response);
			}
			else
			{
				$('#name_icon').removeClass().addClass('fa reg_valid fa-check');
				$('#name_error').html('');
				reg_ready_check();
			}
		}
	});
}
function reg_password_check()
{
	$('#reg_create').attr('disabled', true);
	var pass_check = $('#password').val();
	var error = '';
	if(pass_check.length < 1)
	{
		$('#pass_icon').removeClass();
		$('#pass_error').html('');
	}
	else if(error = password_validate(pass_check, $('#user_name').val()))
	{
		$('#pass_error').html(error);
		$('#pass_icon').removeClass().addClass('fa reg_invalid fa-remove');
	}
	else
	{
		$('#pass_icon').removeClass().addClass('fa reg_valid fa-check');
		$('#pass_error').html('');
		reg_ready_check();
	}
}

function reg_email_check()
{
	$('#reg_create').attr('disabled', true);
	var mail_check = $('#email').val();
	var error = '';
	if(mail_check.length < 1)
	{
		$('#mail_icon').removeClass();
		$('#mail_error').html('');
	}
	else if(error = email_validate(mail_check))
	{
		$('#mail_error').html(error);
		$('#mail_icon').removeClass().addClass('fa reg_invalid fa-remove');
	}
	else
	{
		$('#mail_icon').removeClass().addClass('fa reg_valid fa-check');
		$('#mail_error').html('');
		reg_ready_check();
	}
}

function reg_ready_check()
{
	if($('#mail_icon').hasClass('reg_valid') == true && $('#pass_icon').hasClass('reg_valid') && $('#name_icon').hasClass('reg_valid') && captcha_good == true)
		$('#reg_create').attr('disabled', false);
	else
		$('#reg_create').attr('disabled', true);
}

function register_account()
{
	amp_event('Registration Start');

	$('#reg_create').attr('disabled', true).html('Creating Account...');
	$.ajax({
		type: 'POST',
		url: '/ajax/register_account',
		data:   { user_name: $('#user_name').val(), password: $('#password').val(), email: $('#email').val(), captcha_data: captcha_data, key: xsrf_key },
		success: function(response)
		{
			amp_event('Registration Complete');
			flyover_message(response.message);
			show_verify(1);
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
			$('#reg_create').attr('disabled', false).html('Create a New Account');
  		}
	});

}


function clean_alert(text)
{
	return text.replace(/<br \/>/gi,"\n").replace(/\&quot;/gi,"\"");
}

function warning_prompt(text)
{
	return confirm(text + "\n\nAre you sure you still want to post this?");
}

function show_quoted_message(board_id, topic_id, message_id, xsrf_key)
{
	$.ajax({
		type: 'POST',
		url: '/ajax/forum_get_message',
		data:   { board: board_id, topic: topic_id, message: message_id, key: xsrf_key },
		success: function(response)
		{
			$("#quoted_message").html(response);
			$("#quoted_message").dialog({resizable: true, dialogClass: "reg_dialog", closeText: "X", height: "auto", maxHeight: $(window).height(), width: "80%", modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#quoted_message').dialog('close');});} });
		}
	});
	return false;
}


function forum_show_topic_module(board_id)
{
	if($(document).width() < 750)
		var box_width = "95%";
	else
		var box_width = "60%";

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_topic_module',
		data: {board: board_id, key: xsrf_key},
		success: function(response)
		{
			$('#site_dialog').html(response.content);
			$('#site_dialog').dialog({ resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#site_dialog').dialog('close');});} });
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
    return false;
}

function forum_topic_check()
{
	var topic_title = $("#topic_title").val().trim();

	$(".forum_nt_err").css("text-decoration","none");
	if(topic_title=='')
		$("#post_new_topic").attr("disabled", true);
	else if(topic_title.length < 5)
	{
		$("#post_new_topic").attr("disabled", true);
		$("#topic_err_5").css("text-decoration","underline");
	}
	else if(topic_title.length > 80)
	{
		$("#post_new_topic").attr("disabled", true);
		$("#topic_err_80").css("text-decoration","underline");
	}
	else if(topic_title.match(/[^\x20-\x7f\u2018\u2019\u201C\u201D\u20AC]/))
	{
		$("#post_new_topic").attr("disabled", true);
		$("#topic_err_emoji").css("text-decoration","underline");
	}
	else if(topic_title.toLowerCase() != topic_title && topic_title.toUpperCase() == topic_title )
	{
		$("#post_new_topic").attr("disabled", true);
		$("#topic_err_caps").css("text-decoration","underline");
	}
	else
	{
		$("#post_new_topic").attr("disabled", false);
	}

}

function forum_poll_check()
{
	var poll_ready;
	poll_data['poll_title'] = $("#poll_title").val();
	poll_data['min_level'] = $("#min_level").val();
	var poll_option = {};
	for(var i=1;i<=10;i++)
	{
		if($("#poll_option_" + i).val())
		{
			poll_option[i] = $("#poll_option_" + i).val();
			if(i>1 && poll_data['poll_title'])
				poll_ready = true;
		}
	}
	poll_data['poll_option'] = poll_option;
	if(poll_ready)
		$(".forum_nt_next").attr("disabled", false);
	else
		$(".forum_nt_next").attr("disabled", true);
}


function forum_topic_flair_set(new_id)
{
	$(".flair_option").removeClass("current");
	$("#flair_" + new_id).addClass("current");
}

function gamespace_rate_game(rate_name, score, gameid, key)
{
	$.ajax({
		type: 'POST',
		url: '/ajax/mygames_rate_game',
		data:  { type: rate_name, key: key, score: score, game: gameid },
		success: function(response)
		{
			if(!score)
				score = 0;
			$('#gs_' + rate_name).attr('data-score', score)
			var oldcolor = $("#gs_hint_" + rate_name).css('color');
			$("#gs_hint_" + rate_name).css({ "color": "green" }).animate({ "color": oldcolor }, 500);
			track_event(69);
		}
	});
}

var toggle_block = false;
function toggle_release(gameid,releaseid,xsrf_key,value)
{
	if(toggle_block)
		return;
	toggle_block = true;
	$('.mg_check').attr('disabled', true);
	$.ajax({
		type: 'POST',
		url: '/ajax/mygames_release_toggle',
		data:  { game: gameid, release: releaseid, key: xsrf_key, value: value},
		success: function(response)
		{
			$('#release_select[data-pid="'+gameid+'"]').html(response);
			$('.mg_check').attr('disabled', false);
			toggle_block = false;
		}
	});

}

let vguid_place = '__VIEW_GUID__';
let ccid_place = '[subid_value]';

function uuidv4(){var b="",a,c;for(a=0;32>a;a++){c=16*Math.random()|0;if(8==a||12==a||16==a||20==a)b+="-";b+=(12==a?4:16==a?c&3|8:c).toString(16)}return b};

function add_vguid(el)
{
	el.href = el.href.replace(vguid_place, window.vguid);
}

function add_ccid(el)
{
	var commerceClickId = uuidv4();
	utag_data.commerceClickId = window.commerceClickId = commerceClickId;
	window.commerceClickId = window.commerceClickId.replaceAll('-','');
	el.href = el.href.replace(ccid_place, window.commerceClickId);
}

function lead_click(el, pid)
{
	var clickid = uuidv4();
	amp_event('Monetization Link Clicked', {click_id: clickid});	
	add_vguid(el);
	add_ccid(el);

	if(typeof(om)==='object')
	{
		var leadTrackData = {
			leadDestUrl: el.href,
			leadType: 'LINK',
			merchantName: el.dataset.merchant,
			text: el.dataset.vendorprice
		};
		om.trackLeadClick(leadTrackData);
	}

	setTimeout(function(){el.href = el.href.replace(window.commerceClickId, ccid_place);utag_data.commerceClickId=window.commerceClickId=null;}, 500);
}

function mod_report_show(item_type, item_id, item_name, sub_action = 0, topicality = 0)
{
	var html = '<div class="forum_report"><div class="forum_report_title">Why are you reporting this ' + item_name + '?</div>';

	html += '<div class="forum_report_type">';

	html += '<button id="reason_1" onclick="mod_report_set_reason(1);"><span class="forum_report_type_title">Abusive Behavior</span>Insulting, racist, sexist, threatening, bullying, or other vulgar messages</button>';
	html += '<button id="reason_2" onclick="mod_report_set_reason(2);"><span class="forum_report_type_title">Spamming</span>Advertising a site, channel, or items for sale; asking for codes or money</button>';
	html += '<button id="reason_3" onclick="mod_report_set_reason(3);"><span class="forum_report_type_title">Offensive</span>Sexually explicit, gory, or other obscene content</button>';
	html += '<button id="reason_4" onclick="mod_report_set_reason(4);"><span class="forum_report_type_title">Unmarked Spoilers</span>Plot details not hidden with the spoilers tag</button>';
	if((item_name == 'topic' || item_name == 'comment') && topicality == 1)
		html += '<button id="reason_5" onclick="mod_report_set_reason(5);"><span class="forum_report_type_title">Off-Topic</span>Topics that do not relate to the subject of a message board</button>';
	else if(item_name == 'question')
		html += '<button id="reason_5" onclick="mod_report_set_reason(5);"><span class="forum_report_type_title">Wrong Game / Not a Question</span>This has nothing to do with this game or is not a question</button>';
	html += '<button id="reason_6" onclick="mod_report_set_reason(6);"><span class="forum_report_type_title">Trolling</span>Deliberately provoking users to react negatively</button>';
	html += '<button id="reason_7" onclick="mod_report_set_reason(7);"><span class="forum_report_type_title">None of the Above</span>I\'m reporting this for another reason</button>';
	
	html += '</div>	<div class="forum_report_details">Additional details (<span id="forum_report_not"></span>optional):<input id="reason_text" type="text" /></div>';
	html += '<div class="forum_report_footer"><button id="report_abuse" class="btn btn_primary" disabled="disable" onclick="mod_report_abuse(' + item_type + ', \'' + item_id + '\', 0);">Report Abuse</button>';
	if(sub_action==1)
		html += '<button id="ignore_user" class="btn" disabled="disable" onclick="mod_report_abuse(' + item_type + ', \'' + item_id + '\', 1);">Report and Ignore This User</button>';
	if(sub_action==2)
		html += '<button id="ignore_user" class="btn" disabled="disable" onclick="mod_report_abuse(' + item_type + ', \'' + item_id + '\', 2);">Moderate This Item</button>';
	html += '</div></div>';

	$("#report_dialog").html(html);
	$("#report_dialog").dialog({resizable: true, dialogClass: "reg_dialog", closeText: "X", height: "auto", maxHeight: $(window).height(), width: 400, maxWidth: "90%", modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#report_dialog').dialog('close');});} });

}

function mod_report_set_reason(reason_id)
{
	$(".forum_report_type button").removeClass("selected");
	$("#reason_" + reason_id).addClass("selected");
	$("#report_abuse, #ignore_user").attr("disabled", false);
	$("#reason_text").focus();
	if(reason_id==4 || reason_id==6 || reason_id == 7)
		$("#forum_report_not").html('<b>*not*</b> ');
	else
		$("#forum_report_not").html('');
}

function mod_report_abuse(item_type, item_id, sub_action)
{
	var reason_id = $(".forum_report_type .selected").attr("id").substr(7);
	var reason_text = $("#reason_text").val();

	$.ajax({
		type: 'POST',
		url: '/ajax/mod_report_abuse',
		data:  { item_id: item_id, 
				 item_type: item_type, 
				 key: xsrf_key, 
				 sub_action: sub_action, 
				 reason_id: reason_id, 
				 reason_text: reason_text },
		success: function(response)
		{
			if(response.jump)
				window.location.href = '/moderation/reports?id=' + item_type + '&item=' + item_id;
			else
			{
				$('#report_dialog').dialog('close');
				if(response.success)
					flyover_message(response.success);
			}
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});


}

function flyover_message(message)
{
	$("#flyover").html(message).stop(true, true).slideDown(150).delay(2500).slideUp(500);
}

function user_relationship_set(name, type, tag = '', callback = '')
{
	if(!name || !type)
		return;

	$.ajax({
		type: 'POST',
		url: '/ajax/user_relationship_set',
		data:  { name: name, 
				 type: type, 
				 key: xsrf_key, 
				 tag: tag },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(callback)
				window[callback](response);
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
}

function forum_toggle_favorite(board_id)
{
	var toggle = 0;
	if($("#board_favorite i").hasClass("fa-heart-o"))
		toggle = 1;

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_toggle_favorite',
		data:  { board_id: board_id, 
				 toggle: toggle,
				 key: xsrf_key },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(toggle == 1)
				$("#board_favorite i").removeClass("fa-heart-o").addClass("fa-heart");
			else
			{
				$("#board_favorite i").removeClass("fa-heart").addClass("fa-heart-o");
				$("#board_track i").removeClass("fa-bell").addClass("fa-bell-o");
				$("#board_msg_track i").removeClass("fa-bell").addClass("fa-bell-o");
			}
			if($('#gs_noty i').hasClass('fa-bell'))
				$('.gs_hb_notify i').addClass('fa-bell').removeClass('fa-bell-o');
			else
				$('.gs_hb_notify i').addClass('fa-bell-o').removeClass('fa-bell');		
			if($('#gs_fav i').hasClass('fa-heart'))
				$('.gs_hb_favorite i').addClass('fa-heart').removeClass('fa-heart-o');
			else
				$('.gs_hb_favorite i').addClass('fa-heart-o').removeClass('fa-heart');			
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});

}

function forum_toggle_tracking(board_id, track_type)
{
	var toggle_board = 0;
	var toggle_topic = 0;
	if($("#board_favorite i").hasClass("fa-heart-o"))
		toggle_board = 1;
	if(track_type == 1) // Topics
	{
		if($("#board_track i").hasClass("fa-bell-o"))
			toggle_topic = 1;
		else
			toggle_topic = 0;
	}
	if(track_type == 2) // Messages
	{
		if($("#board_msg_track i").hasClass("fa-bell-o"))
			toggle_topic = 2;
		else
			toggle_topic = 1;
	}

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_toggle_tracking',
		data:  { board_id: board_id, 
				 toggle_board: toggle_board,
				 toggle_topic: toggle_topic,
				 key: xsrf_key },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(toggle_board == 1)
				$("#board_favorite i").removeClass("fa-heart-o").addClass("fa-heart");
			if(toggle_topic == 1)
			{
				$("#board_msg_track i").removeClass("fa-bell").addClass("fa-bell-o");
				$("#board_track i").removeClass("fa-bell-o").addClass("fa-bell");
			}
			else if(toggle_topic == 2)
			{
				$("#board_msg_track i").removeClass("fa-bell-o").addClass("fa-bell");
				$("#board_track i").removeClass("fa-bell-o").addClass("fa-bell");
			}
			else
			{
				$("#board_msg_track i").removeClass("fa-bell").addClass("fa-bell-o");
				$("#board_track i").removeClass("fa-bell").addClass("fa-bell-o");
			}
			if($('#gs_noty i').hasClass('fa-bell'))
				$('.gs_hb_notify i').addClass('fa-bell').removeClass('fa-bell-o');
			else
				$('.gs_hb_notify i').addClass('fa-bell-o').removeClass('fa-bell');		
			if($('#gs_fav i').hasClass('fa-heart'))
				$('.gs_hb_favorite i').addClass('fa-heart').removeClass('fa-heart-o');
			else
				$('.gs_hb_favorite i').addClass('fa-heart-o').removeClass('fa-heart');					
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
	
}

function forum_toggle_topic_tracking(board_id, topic_id)
{
	var toggle_topic = 0;
	if($(".track_topic").hasClass("fa-flag-o"))
		toggle_topic = 1;

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_toggle_topic_tracking',
		data:  { board_id: board_id, 
				 topic_id: topic_id, 
				 toggle_topic: toggle_topic,
				 key: xsrf_key },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(toggle_topic == 1)
				$(".track_topic").removeClass("fa-flag-o").addClass("fa-flag");
			else
				$(".track_topic").removeClass("fa-flag").addClass("fa-flag-o");
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
	
}

function forum_embed_media( str ) 
{
	var matcha;
	var extra = '';
	var auto_url = '';

	if(matcha = str.match(/(?:https?:\/\/)(?:[a-z]+\.dev\.)?gamefaqs\.gamespot\.com\/a\/user_image\/([0-9]\/[0-9]\/[0-9])\/([0-9a-zA-Z_\-\+\/]{12})\.(jpg|png)/i))
	{
		return '<div class="embed_frame"><img src="' + matcha[0] + '" /></div>';
	}
	else if(matcha = str.match(/(?:https?:\/\/)(?:[a-z]+\.dev\.)?gamefaqs\.gamespot\.com\/a\/forum\/([0-9a-f])\/([0-9a-f]{8})\.(jpg|png)/i))
	{
		return '<div class="embed_frame"><img src="' + matcha[0] + '" /></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)(?:www\.|m\.)?(?:youtu\.be\/|youtube\.(?:com|jp|co\.uk|com\.au)\/(?:watch|shorts)(?:\?v=|\/){1})([a-zA-Z0-9\-_]{11})((?:\?|\&amp;)t=[0-9]+(?:(?:m|s)?(?:[0-9]+s)?)?)?/i))
	{
		if(matcha[2])
			extra = matcha[2].replace(/(\?|&)t=/, '&start=');
		return '<div class="embed_frame"><iframe width="540" height="315" class="yt_iframe" src="https://www.youtube.com/embed/' + matcha[1] +'?rel=0'+ extra +'" frameborder="0" allow="encrypted-media" allowfullscreen></iframe></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)(?:www\.|m\.|i\.)?imgur\.com\/(?:a|gallery)\/([a-zA-Z0-9_]{5,10})/i))
	{
		return '<div class="embed_frame"><blockquote class="imgur-embed-pub" lang="en" data-id="a/'+matcha[1]+'"><a href="//imgur.com/a/'+matcha[1]+'">via Imgur</a></blockquote><scr'+'ipt async src="//s.imgur.com/min/embed.js" charset="utf-8"></scr'+'ipt></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)(?:www\.|m\.|i\.)?imgur\.com\/([a-zA-Z0-9_]{5,10})(\.(?:gif|jpg|jpeg|webm))?/i))
	{
		return '<div class="embed_frame"><blockquote class="imgur-embed-pub" lang="en" data-id="'+matcha[1]+'"><a href="//imgur.com/'+matcha[1]+'">via Imgur</a></blockquote><scr'+'ipt async src="//s.imgur.com/min/embed.js" charset="utf-8"></scr'+'ipt></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)(?:[a-zA-Z]{3,10}\.)?(?:gfycat\.com\/([a-zA-Z_]{5,60}))(\.(?:gif|webm))?/i))
	{
		auto_url = ''; // auto_url = '?autoplay=0';
		return '<div class="embed_frame"><iframe width="540" height="315" src="https://gfycat.com/ifr/'+matcha[1]+auto_url+'" frameborder="0" allowfullscreen><p><a href="https://gfycat.com/'+matcha[1]+'">via Gfycat</a></iframe></div>';		
	}
	else if (matcha = str.match(/(?:https?:\/\/)streamable\.com\/([a-zA-Z0-9_\-]{4,60})/i))
	{
		return '<div class="embed_frame"><iframe width="540" height="315" src="https://streamable.com/e/'+matcha[1]+'" frameborder="0" autoplay="on" allowfullscreen></iframe></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)giphy\.com\/(?:gifs\/|.*-)([a-zA-Z0-9_\-]{5,60})/i))
	{
		return '<div class="embed_frame"><iframe src="https://giphy.com/embed/'+matcha[1]+'" frameBorder="0" class="giphy-embed" allowFullScreen></iframe></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)(?:www\.|mobile\.|i\.)?(?:twitter\.|x\.)com\/([a-z0-9_\-]{1,60})\/status\/([0-9]{10,60})/i))
	{
		return '<div class="embed_frame"><blockquote class="twitter-tweet"><a href="//twitter.com/'+matcha[1]+'/status/'+matcha[2]+'">via X/Twitter</a></blockquote><scr'+'ipt async src="https://platform.twitter.com/widgets.js"" charset="utf-8"></sc'+'ript></div>';
	}
	else if (matcha = str.match(/(?:https?:\/\/)(?:www\.)?twitch.tv\/videos\/([0-9]{5,60})/i))
	{
		return '<div class="embed_frame"><iframe src="https://player.twitch.tv/?video='+matcha[1]+'&parent=gamefaqs.gamespot.com" height="315" width="540" allowfullscreen="allowfullscreen"></iframe></div>';
	}
	else
		return '<a rel="nofollow" href="' + str + '">' + str + '<\/a>';
}

function forum_click_to_embed( str ) 
{
	var embed = false;

	if(str.match(/(?:https?:\/\/)(?:[a-z]+\.dev\.)?gamefaqs\.gamespot\.com\/a\/user_image\/([0-9]\/[0-9]\/[0-9])\/([0-9a-zA-Z_\-\+\/]{12})\.(jpg|png)/i))
		embed = true;
	else if(str.match(/(?:https?:\/\/)(?:[a-z]+\.dev\.)?gamefaqs\.gamespot\.com\/a\/forum\/([0-9a-f])\/([0-9a-f]{8})\.(jpg|png)/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)(?:www\.|m\.)?(?:youtu\.be\/|youtube\.(?:com|jp|co\.uk|com\.au)\/(?:watch|shorts)(?:\?v=|\/){1})([a-zA-Z0-9\-_]{11})((?:\?|\&amp;)t=[0-9]+(?:(?:m|s)?(?:[0-9]+s)?)?)?/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)(?:www\.|m\.|i\.)?imgur\.com\/(?:a|gallery)\/([a-zA-Z0-9_]{5,10})/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)(?:www\.|m\.|i\.)?imgur\.com\/([a-zA-Z0-9_]{5,10})(\.(?:gif|jpg|jpeg|webm))?/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)(?:[a-zA-Z]{3,10}\.)?(?:gfycat\.com\/([a-zA-Z_]{5,60}))(\.(?:gif|webm))?/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)streamable\.com\/([a-zA-Z0-9_\-]{4,60})/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)giphy\.com\/(?:gifs\/|.*-)([a-zA-Z0-9_\-]{5,60})/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)(?:www\.|mobile\.|i\.)?(?:twitter\.|x\.)com\/([a-z0-9_\-]{1,60})\/status\/([0-9]{10,60})/i))
		embed = true;
	else if (str.match(/(?:https?:\/\/)(?:www\.)?twitch.tv\/videos\/([0-9]{5,60})/i))
		embed = true;

	if(embed)
		return '<span class="click_embed" data-src="' + str + '"><i class="plusbox fa fa-plus-square-o"></i>&nbsp;' + str + '<\/span> <a rel="nofollow" class="embed_link" href="' + str + '"><i class="fa fa-external-link"></i></a>';
	else
		return '<a rel="nofollow" href="' + str + '">' + str + '<\/a>';
}

function forum_embed_image( str )
{
	if(matcha = str.match(/(?:https?:\/\/)(?:[a-z]+\.dev\.)?gamefaqs\.gamespot\.com\/a\/user_image\/([0-9]\/[0-9]\/[0-9])\/([0-9a-zA-Z_\-\+\/]{12})\.(jpg|png)/i))
		return '<img src="' + matcha[0] + '" />';
	else if(matcha = str.match(/(?:https?:\/\/)(?:[a-z]+\.dev\.)?gamefaqs\.gamespot\.com\/a\/forum\/([0-9a-f])\/([0-9a-f]{8})\.(jpg|png)/i))
		return '<img src="' + matcha[0] + '" />';
	else
		return forum_click_to_embed(str);
}

function forum_link_media( str ) 
{
	return '<a rel="nofollow" href="' + str + '">' + str + '<\/a>';
}

function forum_convert_links(link_type, target)
{
	if(link_type==1 || link_type == 0)
		$(target).each(function() {
			$(this).html( $(this).html().replace(/http(s)?:\/\/([\w+?\.\w+])+([a-zA-Z0-9\~\!\@\#\$\%\^\&amp;\*\(\)_\-\=\+\\\/\?\.\:\;'\,]*[^!@\^()\[\]\{\}|\\\:;'",.?<>`\s])?/ig, forum_embed_image));
		});
	if(link_type==2)
		return;
	if(link_type==3)
		$(target).each(function() {
			$(this).html( $(this).html().replace(/http(s)?:\/\/([\w+?\.\w+])+([a-zA-Z0-9\~\!\@\#\$\%\^\&amp;\*\(\)_\-\=\+\\\/\?\.\:\;'\,]*[^!@\^()\[\]\{\}|\\\:;'",.?<>`\s])?/ig, forum_embed_media));
		});
	if(link_type==4)
		$(target).each(function() {
			$(this).html( $(this).html().replace(/http(s)?:\/\/([\w+?\.\w+])+([a-zA-Z0-9\~\!\@\#\$\%\^\&amp;\*\(\)_\-\=\+\\\/\?\.\:\;'\,]*[^!@\^()\[\]\{\}|\\\:;'",.?<>`\s])?/ig, forum_click_to_embed));
		});
	if(link_type==5)
		$(target).each(function() {
			$(this).html( $(this).html().replace(/http(s)?:\/\/([\w+?\.\w+])+([a-zA-Z0-9\~\!\@\#\$\%\^\&amp;\*\(\)_\-\=\+\\\/\?\.\:\;'\,]*[^!@\^()\[\]\{\}|\\\:;'",.?<>`\s])?/ig, forum_link_media));
		});

	$(target + " .click_embed").click( function() {
		if(!$(this).hasClass('opened'))
		{
			$(this).addClass('opened');
			$(this).children('.plusbox').removeClass('fa-plus-square-o').addClass('fa-minus-square-o');
			$(this).next('.embed_link').hide();
			$(this).after(forum_embed_media($(this).attr("data-src")));
		}
		else
		{
			$(this).removeClass('opened');
			$(this).children('.plusbox').removeClass('fa-minus-square-o').addClass('fa-plus-square-o');
			$(this).next('.embed_frame').remove();
			$(this).next('.embed_link').show();
		}
	});

	if(link_type==0)
		$(".click_embed").first().click();
}

function forum_google_set_rec_val(val, board_id, topic_id)
{
	if(val==1 || val==5)
	{
		$('#rec_one, #rec_two').hide();
		$('#rec_three').show();
		setTimeout(function()
		{
			$('#contrib_rec').slideUp(300, function(){ $(this).remove(); });
		}, 2000);
	}
	else if(val==2)
	{
		$('#rec_one').hide();
		$('#rec_two').show();
	}
	else
	{
		$('#contrib_rec').remove();
	}

	if(val>=1 && val<=5)
	{
		$.ajax({
			type: 'POST',
			url: '/ajax/forum_google_log',
			data:  { b: board_id, t: topic_id, btn: val, key: xsrf_key}
		});
	}
	return;
}


function forum_toggle_quotes(mid)
{
	$('.msg_body[name="'+mid+'"] blockquote > blockquote > blockquote:not(.expand_quote)').css('display','block');
	$('blockquote.expand_quote[data-msgid="'+mid+'"]').remove();
}


function forum_textcomplete_init(name)
{
	$('textarea[name="'+name+'"]').textcomplete(
		[{
			match: /(^|\B)@([\-\w\d]{2,})$/,
			search: function (term, callback) {
				term = term.toLowerCase();
				callback($.map(user_list, function(word) {
					return word.toLowerCase().indexOf(term) === 0 ? word : null;
				}));
			},
			index: 2,
			replace: function(word) {
				return '@' + word;
			}
	}]);
}


function forum_toggle_user_menu(mid, name)
{
	$('.user_tag_input').hide();
	if($('#userpop_' + mid + ' .user_submenu').length == 0)
	{
		$('.user_submenu').remove();

		$.ajax({
				type: 'POST',
				url: '/ajax/community_profile_popup',
					data:  { name: name, callback: 'forum_update_message_list', key: xsrf_key},
					success: function(response)
					{
						$('#userpop_' + mid).append(response);
						$('#userpop_' + mid + ' .user_submenu').show();
					}
		});
	}
	else
	{
		$('#userpop_' + mid + ' .user_submenu').remove();
	}
}

function forum_update_message_list(response)
{
	if(response.tag)
	{
		if(!$('.tag_' + response.tag).length )
			$('.uid_' + response.tag).append('<span class="tag tag_' + response.tag + '"></span>');
		$('.tag_' + response.tag).html(escape_html(response.tag_text));
	}
	if(response.follow)
		$(".uid_" + response.follow).parent('.msg_infobox').addClass("friend");
	if(response.unfollow)
		$(".uid_" + response.unfollow).parent('.msg_infobox').removeClass("friend");
	if(response.mute)
		$(".uid_" + response.mute).parent('.msg_infobox').parent('.msg').hide();
}

function forum_cb_update(board_id, action, user_name)
{
	if(action=='remove')
		if(!confirm('Are you certain you want to remove ' + user_name + ' from this board?'))
			return;
	if(action=='promote')
		if(!confirm('Are you certain you want to promote ' + user_name + ' to leadership of this board? Leaders can add and remove members, as well as delete topics and messages'))
			return;
	if(action=='demote')
		if(!confirm('Are you certain you want to demote ' + user_name + ' from leadership of this board?'))
			return;
	if(action=='unblock')
		if(!confirm('Are you certain you want to unblock ' + user_name + ' from this board?'))
			return;
	if(action=='accept')
		if(!confirm('Are you certain you want to accept the invitation request of ' + user_name + ' for this board?'))
			return;
	if(action=='reject')
		if(!confirm('Are you certain you want to reject the invitation request of ' + user_name + ' for this board?'))
			return;

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_cb_update',
		data:  { board_id: board_id, user_name: user_name, action: action, key: xsrf_key },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(response.refresh)
				window.location.reload();
			if(response.add_row)
				$('#member_list').append(response.add_row);
			if(response.remove_row)
				$('#member_list_' + response.remove_row).remove();

		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});


}

function forum_topic_control(board_id, topic_id, action, target_id = 0)
{

	if(action == 'end_poll')
	{
		if(!confirm('Are you certain you want to end this poll? No more voting will be allowed and this action cannot be undone.'))
			return;
	}
	else if(action != 'flair')
	{
		if(!confirm('Are you certain you want to ' + action + ' this topic?'))
			return;
	}

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_topic_control',
		data:  { board_id: board_id, topic_id: topic_id, action: action, target_id: target_id, key: xsrf_key },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(response.refresh)
				window.location.reload();
			if(response.location)
				window.location = response.location;
			if(response.remove)
				$(response.remove).remove();
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
}

function forum_message_control(board_id, topic_id, message_id, action)
{

	if(!confirm('Are you certain you want to ' + action + ' this message?'))
		return;

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_message_control',
		data:  { board_id: board_id, topic_id: topic_id, action: action, message_id: message_id, key: xsrf_key },
		success: function(response)
		{
			if(response.success)
				flyover_message(response.success);
			if(response.refresh)
				window.location.reload();
			if(response.location)
				window.location = response.location;
			if(response.remove)
				$(response.remove).remove();
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
}

function get_msg_tag_buttons(msgid,cnt,post)
{
	var tags = '<span class="tagbuttons '+msgid+'">' +
		'<input tabindex="-1" title="Ctrl+B" name="b" class="btn btn_mini btnbold" type="button" value="Bold" onclick="txtTag(\'b\',\''+msgid+'\')"/>' +
		'<input tabindex="-1" title="Ctrl+I" name="i" class="btn btn_mini btnitalic" type="button" value="Italic" onclick="txtTag(\'i\',\''+msgid+'\')"/>';
	if(post==1)
		tags += '<input tabindex="-1" title="Ctrl+S" name="spoiler" class="btn btn_mini" type="button" value="Spoiler" onclick="txtTag(\'spoiler\',\''+msgid+'\')"/>' +
		'<input tabindex="-1" title="Ctrl+E" name="cite" class="btn btn_mini btncite" type="button" value="Cite" onclick="txtTag(\'cite\',\''+msgid+'\')"/>' +
		'<input tabindex="-1" title="Ctrl+Q" name="quote" class="btn btn_mini" type="button" value="Quote" onclick="txtTag(\'quote\',\''+msgid+'\')"/>' +
		'<input tabindex="-1" title="Ctrl+D" name="code" class="btn btn_mini btncode" type="button" value="Code" onclick="txtTag(\'code\',\''+msgid+'\')"/>';
	tags += '</span>';
	tags += '<br/>';
	var ctrlBtn = false;
	var ctrlHeld = false;
	var msgArea = $('textarea[name="'+msgid+'"]');

	$(msgArea).before(tags);

	$(msgArea).blur(function(){ctrlBtn=false;ctrlHeld=false;});

	$(msgArea).keyup(function(e){
		if(e.which==17){ctrlBtn=false;ctrlHeld=false;}
		if(e.which==18 && ctrlHeld) ctrlBtn=true;
		if(post==1)
			msg_cc($(msgArea),cnt,'post');
	});

	$(msgArea).keydown(function(e){
		if(e.which==17){ctrlBtn=true;ctrlHeld=true;}
		if(e.which==18) ctrlBtn=false;
		if(e.which==66 && ctrlBtn){e.stopPropagation();e.preventDefault();txtTag('b',msgid);}
		else if(e.which==68 && ctrlBtn && post==1){e.stopPropagation();e.preventDefault();txtTag('code',msgid);}
		else if(e.which==69 && ctrlBtn && post==1){e.stopPropagation();e.preventDefault();txtTag('cite',msgid);}
		else if(e.which==73 && ctrlBtn){e.stopPropagation();e.preventDefault();txtTag('i',msgid);}
		else if(e.which==81 && ctrlBtn && post==1){e.stopPropagation();e.preventDefault();txtTag('quote',msgid);}
		else if(e.which==83 && ctrlBtn && post==1){e.stopPropagation();e.preventDefault();txtTag('spoiler',msgid);}
		if(post==1)
			msg_cc($(msgArea),cnt,'post');
	});

	if(post==1)
		msg_cc($(msgArea),cnt,'post');
	return;
}

function msg_cc(field,cnt,type)
{
	var msg = $(field);
	var cntdisp = (cnt*0.25);
	if($(field).val().length < (cnt * 0.75))
	{
		$('.charcount.'+$(field).attr('name')).empty();
		return;
	}
	if(type=='post')
		cnt -= (($(field).val().split(/\n|\r|"/).length - 1) * 5) + (($(field).val().split(/&/).length - 1) * 4) + (($(field).val().split(/>|</).length - 1) * 3);
	else if(type=='pm')
		cnt -= (($(field).val().split(/\n|\r/).length) - 1);
	cnt -= ($(msg).val().length);
	var cc = $('.charcount.'+$(field).attr('name'));
	if(cnt<=cntdisp)
		$(cc).html(cnt+' characters remaining');
	else
		$(cc).empty();
	$(cc).css(cnt<0 ? {color:'#f00'} : {color:''});
}

function sub_cc(field,type)
{
	var sub = $(field);
	if(type=='topictitle')
	{
		if($(sub).val().match(/[\u0100-\u2017\u201E-\uffff]/))
		{
			$('.charcount.'+$(field).attr('name')).html('Warning: Unicode characters are removed from topic titles');
			return;
		}
		var cnt = 80;
		var cntdisp = 20;
		cnt -= $(sub).val().length + (($(field).val().split(/>|</).length - 1) * 3) + (($(field).val().split(/&/).length - 1) * 4) + (($(field).val().split(/"/).length - 1) * 5);
	}
	else if(type=='subject')
	{
		if($(sub).val().match(/[\u0100-\u2017\u201E-\uffff]/))
		{
			$('.charcount.'+$(field).attr('name')).html('Warning: Unicode characters are removed from PM subjects');
			return;
		}
		var cnt = 100;
		var cntdisp = 25;
		cnt -= $(sub).val().length;
	}
	else if(type=='poll_text')
	{
		if($(sub).val().match(/[\u0100-\u2017\u201E-\uffff]/))
		{
			$('.charcount.'+$(field).attr('name')).html('Warning: Unicode characters are removed from poll titles');
			return;
		}
		var cnt = 200;
		var cntdisp = 50;
		cnt -= $(sub).val().length + (($(field).val().split(/>|</).length - 1) * 3) + (($(field).val().split(/&/).length - 1) * 4) + (($(field).val().split(/"/).length - 1) * 5);
	}
	var cc = $('.charcount.'+$(field).attr('name'));
	if(type=='topictitle' && cnt<=cntdisp)
		$(cc).html(cnt+' characters remaining (5-80 characters allowed)');
	else if(type=='subject' && cnt<=cntdisp)
		$(cc).html(cnt+' characters remaining (2-100 characters allowed)');
	else if(type=='poll_text' && cnt<=cntdisp)
		$(cc).html(cnt+' characters remaining (5-200 characters allowed)');
	else
		$(cc).empty();
	$(cc).css(cnt<0 ? {color:'#f00'} : {color:''});
}

function txtTag(tag,name)
{
	var msgArea = $('textarea[name="'+name+'"]');
	var currTag = $('.tagbuttons.'+name+' input[name="'+tag+'"]');
	var tagStart = "<"+tag+">";
	var tagEnd = "</"+tag+">";
	var c = $(msgArea)[0].selectionStart;
	var selPre = $(msgArea).val().substr(0,c);
	var selPost = $(msgArea).val().substr($(msgArea)[0].selectionEnd);
	var selTxt;

	if(c!=undefined)
	{
		selTxt = $(msgArea).val().substr(c,$(msgArea)[0].selectionEnd-c);
	}
	if(selTxt.length<1)
	{
		if($(currTag).hasClass('active'))
		{
			$(msgArea).val([$(msgArea).val().slice(0,c),tagEnd,$(msgArea).val().slice(c)].join(''));
			$(currTag).removeClass('active').css('color','#000');
			var p = c+tagEnd.length;
			setPos($(msgArea),p);
		}
		else
		{
			$(msgArea).val([$(msgArea).val().slice(0,c),tagStart,$(msgArea).val().slice(c)].join(''));
			var p = c+tagStart.length;
			$(currTag).addClass('active').css('color','#6564ff');
			setPos($(msgArea),p);
		}
	}
	else
	{
		$(msgArea).val(selPre+tagStart+selTxt+tagEnd+selPost);
		var p = c+tagStart.length+selTxt.length+tagEnd.length;
		setPos($(msgArea),p);
	}
}

function setPos(m,p)
{
	if($(m)[0].setSelectionRange)
	{
		$(m)[0].focus();
		$(m)[0].setSelectionRange(p,p);
	}
	else if($(m)[0].createTextRange)
	{
		var r = $(m)[0].createTextRange();
		r.collapse(true);
		r.moveEnd('character',p);
		r.moveStart('character',p);
		r.select();
	}
}

function quick_quote(board_id,topic_id,message_id,xsrf_key,wysiwyg)
{
	if(window.getSelection().toString().length>0)
	{
		var mb = window.getSelection().getRangeAt(0).startContainer;
		var msghi = mb.parentNode.getAttribute('name');
		if(msghi==null)
		{
			while(mb.className!='msg_body' && mb.className!='msg_body newbeta')
				mb = mb.parentNode;
			msghi = mb.getAttribute('name');
		}
		var msghitxt = window.getSelection().toString();
		if(msghi==message_id)
		{
			$.ajax({
				type: 'POST',
				url: '/ajax/forum_quote_message',
				data: {bid: board_id, tid: topic_id, mid: message_id, hi: 1, key: xsrf_key},
				success: function(response)
				{
					var d = response.quote;
					if(response.error)
					{
						alert(clean_alert(response.error));
					}
					else if(wysiwyg)
					{
						d += "<br /><blockquote>"+msghitxt.replace(/\r\n|\r|\n/gi, "<br />")+"</blockquote>";
						if($('#quill_message_new .ql-editor').text())
							quill_new.clipboard.dangerouslyPasteHTML($('#quill_message_new .ql-editor').html() + d);
						else
							quill_new.clipboard.dangerouslyPasteHTML(d);
						quill_new.insertText(quill_new.getLength(), '\n');
						quill_new.setSelection(quill_new.getLength());
						quill_new.focus();

					}
					else
					{
						var msg = $('textarea[name="messagetext"]');
						d += "&lt;quote&gt;"+msghitxt+"&lt;/quote&gt;";
						var s = d.replace(/\&lt;/gi,"<").replace(/\&gt;/gi,">").replace(/\&amp;/gi,"&").replace(/\&quot;/gi,'"');
						$(msg).val($(msg).val()+s+"\r");
						var val = $(msg).val();
						setPos(document.getElementsByName('messagetext')[0],val.length);
					}
				}
			});
		}
	}
	else
	{
		$.ajax({
			type: 'POST',
			url: '/ajax/forum_quote_message',
			data: {bid: board_id, tid: topic_id, mid: message_id, wysi: wysiwyg, key: xsrf_key},
			success: function(response)
			{
				var d = response.quote;
				if(response.error)
				{
					alert(clean_alert(response.error));
				}
				else if(wysiwyg)
				{
					if($('#quill_message_new .ql-editor').text())
						quill_new.clipboard.dangerouslyPasteHTML($('#quill_message_new .ql-editor').html() + d);
					else
						quill_new.clipboard.dangerouslyPasteHTML(d);
					quill_new.insertText(quill_new.getLength(), '\n');
					quill_new.setSelection(quill_new.getLength());
					quill_new.focus();

				}
				else
				{
					var msg = $('textarea[name="messagetext"]');
					var s = d.replace(/\&lt;/gi,"<").replace(/\&gt;/gi,">").replace(/\&amp;/gi,"&").replace(/\&quot;/gi,'"');
					$(msg).val($(msg).val() + s);
					var val = $(msg).val();
					setPos(document.getElementsByName('messagetext')[0],val.length);
				}
			}
		});
	}
}

function forum_post_new_message(board_id, topic_id, override = 0)
{

	if(!$("#quill_message_new").length)
	{
		var message_text = $("#messagetext").val();
		var is_wysiwyg = 0;
	}
	else
	{
		var is_wysiwyg = 1;
		var message_text = $("#quill_message_new .ql-editor").html()
		if($("#quill_message_new .ql-editor").html().length > 1024 * 1024 * 8)
		{
			alert("The maximum size of a post with images is 8MB. You need to remove some images or include smaller versions of them.");
			return;
		}
	}

	$("#post_new_message").prop('disabled', true).text('Processing...');

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_post_message',
		data: {board: board_id, topic: topic_id, message: message_text, is_wysiwyg: is_wysiwyg, key: xsrf_key, override: override},
		success: function(d)
		{
			if(d.status=='error')
			{
				alert(clean_alert(d.status_text));
				$("#post_new_message").prop('disabled', false).text('Post New Message');
			}
			else if(d.status=='warning')
			{
				if(warning_prompt(clean_alert(d.warnings)))
				{
					forum_post_new_message(board_id, topic_id, 1);
				}
				else
					$("#post_new_message").prop('disabled', false).text('Post New Message');
			}
			else
			{
				var new_location = d.message_url.substr(0, d.message_url.indexOf('#'));
				var current_location = window.location.pathname + window.location.search;
				window.location.href = d.message_url;
				if(new_location == current_location)
					location.reload(true);
			}


		}
	});
}

function edit_message(board_id, topic_id, message_id, div_id)
{
	$.ajax({
		type: 'POST',
		url: '/ajax/forum_get_edit_message',
		data: {board: board_id, topic: topic_id, message: message_id, div_id: div_id, key: xsrf_key},
		success: function(response)
		{
			if(response)
			{
				if($("#msg_edit").attr('data-id'))
				{
					$("#msg_" + $("#msg_edit").attr('data-id') + " .msg_body").show();
					$("#msg_" + $("#msg_edit").attr('data-id') + " .msg_below").show();
				}

				$("#msg_edit").remove();
				$("#msg_" + div_id + " .msg_body").hide();
				$("#msg_" + div_id + " .msg_below").hide();
				$("#msg_" + div_id).prepend('<div id="msg_edit" data-id="' + div_id + '"></div>');
				$("#msg_edit").html(response);
			}
			else
			{
				$("#msg_" + div_id + " .action_after").text("This message cannot be edited at this time");
			}
		}
	});

}

function cancel_edit(div_id)
{
	$("#msg_" + div_id + " .msg_body").show();
	$("#msg_" + div_id + " .msg_below").show();
	$("#msg_edit").remove();
}

function forum_save_edit(board_id, topic_id, message_id, override = 0)
{
	if(!$("#quill_message_edit").length)
	{
		var message_text = $("#edit_" + message_id).val();
		var is_wysiwyg = 0;
	}
	else
	{
		var is_wysiwyg = 1;
		var message_text = $("#quill_message_edit .ql-editor").html()
		if($("#quill_message_edit .ql-editor").html().length > 1024 * 1024 * 8)
		{
			alert("The maximum size of a post with images is 8MB. You need to remove some images or include smaller versions of them.");
			return;
		}
	}

	$("#save_edit").prop('disabled', true).text('Processing...');

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_save_edit_message',
		data: {board: board_id, topic: topic_id, message: message_id, message_text: message_text, is_wysiwyg: is_wysiwyg, key: xsrf_key, override: override},
		success: function(d)
		{
			if(d.status=='error')
			{
				alert(clean_alert(d.status_text));
				$("#save_edit").prop('disabled', false).text('Save Changes');

			}
			else if(d.status=='warning')
			{
				if(warning_prompt(clean_alert(d.warnings)))
					forum_save_edit(board_id, topic_id, message_id, 1);
				else
					$("#save_edit").prop('disabled', false).text('Save Changes');
			}
			else
			{
				window.location.href = d.message_url;
				location.reload(true);
			}
		}
	});
}

function forum_post_new_topic(board_id, override = 0)
{
	if(!$("#quill_message_topic").length)
	{
		var message_text = $("#messagetext").val();
		var is_wysiwyg = 0;
	}
	else
	{
		var is_wysiwyg = 1;
		var message_text = $("#quill_message_topic .ql-editor").html()
		if($("#quill_message_topic .ql-editor").html().length > 1024 * 1024 * 8)
		{
			alert("The maximum size of a post with images is 8MB. You need to remove some images or include smaller versions of them.");
			return;
		}
	}

	if($('.flair_select .flair.current').length)
		var flair_id = $('.flair_select .flair.current').attr('id').substr(6);
	else
		var flair_id = 1;

	$("#post_new_topic").prop('disabled', true).text('Processing...');

	var poll_data = {};
	if($("#forum_nt_poll").is(':visible'))
	{
		poll_data['poll_title'] = $("#poll_title").val();
		poll_data['min_level'] = $("#min_level").val();
		var poll_option = {};
		for(var i=1;i<=10;i++)
		{
			if($("#poll_option_" + i).val())
				poll_option[i] = $("#poll_option_" + i).val();
		}
		poll_data['poll_option'] = poll_option;
	}

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_post_topic',
		data: {board: board_id, topic: $("#topic_title").val(), flair: flair_id, poll: JSON.stringify(poll_data), message: message_text, override: override, key: xsrf_key, is_wysiwyg: is_wysiwyg},
		success: function(d)
		{
			if(d.status=='error')
			{
				alert(clean_alert(d.status_text));
				$("#post_new_topic").prop('disabled', false).text('Create New Topic');
			}
			else if(d.status=='warning')
			{
				if(warning_prompt(clean_alert(d.warnings)))
					forum_post_new_topic(board_id, 1);
				else
					$("#post_new_topic").prop('disabled', false).text('Create New Topic');
			}
			else
			{
				window.location.href = d.topic_url;
			}

		}
	});
}

function forum_preview_new_message(board_id, topic_id)
{
	if($("#quill_message_new").length)
	{
		var is_wysiwyg = 1;
		var message_text = $("#quill_message_new .ql-editor").html()
		if($("#quill_message_new .ql-editor").html().length > 1024 * 1024 * 8)
		{
			alert("The maximum size of a post with images is 8MB. You need to remove some images or include smaller versions of them.");
			return;
		}
	}
	else if ($("#quill_message_topic").length)
	{
		var is_wysiwyg = 1;
		var message_text = $("#quill_message_topic .ql-editor").html()
		if($("#quill_message_topic .ql-editor").html().length > 1024 * 1024 * 8)
		{
			alert("The maximum size of a post with images is 8MB. You need to remove some images or include smaller versions of them.");
			return;
		}
	}	
	else 
	{
		var message_text = $("#messagetext").val();
		var is_wysiwyg = 0;
	}

	if($('.flair_select .flair.current').length)
		var flair_id = $('.flair_select .flair.current').attr('id').substr(6);
	else
		var flair_id = 1;

	var poll_data = {};
	if($("#forum_nt_poll").is(':visible'))
	{
		poll_data['poll_title'] = $("#poll_title").val();
		poll_data['min_level'] = $("#min_level").val();
		var poll_option = {};
		for(var i=1;i<=10;i++)
		{
			if($("#poll_option_" + i).val())
				poll_option[i] = $("#poll_option_" + i).val();
		}
		poll_data['poll_option'] = poll_option;
	}

	$.ajax({
		type: 'POST',
		url: '/ajax/forum_preview_message',
		data: {board: board_id, topic: topic_id, topic_title: $("#topic_title").val(), flair: flair_id, poll: JSON.stringify(poll_data), message: message_text, key: xsrf_key, is_wysiwyg: is_wysiwyg},
		success: function(d)
		{
			if(d.status=='error')
			{
				alert(clean_alert(d.status_text));
			}
			else
			{
				$("#quoted_message").html(d.formatted_message_text);
				$("#quoted_message").dialog({resizable: true, dialogClass: "reg_dialog", closeText: "X", height: "auto", maxHeight: $(window).height(), width: "80%", modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#quoted_message').dialog('close');});} });
			}


		}
	});
}


function qna_show_ask_module(pid, page_type = '')
{
	if($(document).width() < 750)
		var box_width = "95%";
	else
		var box_width = "60%";

	$.ajax({
		type: 'POST',
		url: '/ajax/qna_ask_module',
		data: {pid: pid, ptt: page_type, key: xsrf_key},
		success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true });
		},
		error: function (xhr)
     	{
     		var message = JSON.parse(xhr.responseText);
     		alert(message.error);
  		}
	});
}

function qna_question_check()
{
	var question = $("#question").val().trim();

	$(".qna_err").css("text-decoration","none");
	$(".qna_ask_warning.qtitle").html('');
	if(question=='')
		$(".qna_ask_next").attr("disabled", true);
	else if(question.split(" ").length < 3)
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_words").css("text-decoration","underline");
	}
	else if(question.length < 15)
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_15").css("text-decoration","underline");
	}
	else if(question.substr(-1, 1)!='?')
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_mark").css("text-decoration","underline");
	}
	else if(question.length > 120)
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_120").css("text-decoration","underline");
	}
	else
	{
		$(".qna_ask_next").attr("disabled", false);
		$(".qna_ask_question").text(question);
		if(question.match(/(fuck|shit|bitch)/i))
			$(".qna_ask_warning.qtitle").html("Please do not use inappropriate language in your question.");
		else if(question.match(/(give me|trade|event code|friend code|send me|friend safari)/i))
			$(".qna_ask_warning.qtitle").html("Please do not use Q&amp;A to trade items or exchange codes; use the message boards instead.");
		else if (!question.match(/^(can|who|why|where|when|what|is|do|how|does|will|which|are|should|could)/i))
			$(".qna_ask_warning.qtitle").html("Make sure your question is a full sentence; &quot;How&quot;, &quot;Where&quot;, and &quot;What&quot; are the most common ways to start.");
		else if(question.match(/(worth buying)/i))
			$(".qna_ask_warning.qtitle").html("Please do not use Q&amp;A to ask if a game is worth buying; use the message boards or read its reviews instead.");
		else
			$(".qna_ask_warning.qtitle").html('');
	}

	if($('.flair_select .flair.current').length==0)
	{
		$('.qna_ask_warning.qflair').html('You must select a valid question type.');
		$('.qna_ask_next').attr('disabled', true);
	}
	else
	{
		$('.qna_ask_warning.qflair').html('');
		$(".qna_ask_flair").text($('.flair_select .flair.current').text());
	}
}

function qna_details_check()
{
	var details = $("#details").val().trim();

	$(".qna_err").css("text-decoration","none");
	$(".qna_ask_warning.qbody").html('');

	if(details=='')
		$(".qna_ask_next").attr("disabled", true);
	else if(details.split(" ").length < 5)
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_words").css("text-decoration","underline");
	}
	else if(details.length < 25)
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_25").css("text-decoration","underline");
	}
	else if(details.length > 4000)
	{
		$(".qna_ask_next").attr("disabled", true);
		$("#qna_err_4000").css("text-decoration","underline");
	}
	else
	{
		$(".qna_ask_next").attr("disabled", false);
		$(".qna_ask_details").html(details.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/\n/g, "<br />"));
		if(details.match(/(fuck|shit|bitch|nig|cunt)/i))
			$(".qna_ask_warning.qbody").html("Please do not use inappropriate language in your question details.");
		else if(details.match(/https:\/\/(?!gamefaqs\.gamespot\.com)/i))
			$(".qna_ask_warning.qbody").html("Only links to other GameFAQs pages are allowed in Q&amp;A.");
	}
}

function qna_spoiler()
{
	$("#qna_spoiler").html('');
	if($("#spoiler").prop('checked'))
		$("#qna_spoiler").html("This question contains spoilers, so we'll hide the title for people who haven't finished the game yet.");
}


function qna_flair_set(new_id)
{
	$(".flair_select .flair_option").removeClass("current");
	$(".flair_select #flair_" + new_id).addClass("current");
}

function qna_check_question(step)
{
	if($('.flair_select .flair.current'))
		var category = $('.flair_select .flair.current').attr('data-id');
	else
		var category = 0;

	var details = $("#details").val()
	if(step==2)
		details = 'this is a dummy 25 character detail';
	$(".qna_ask_next").prop("disabled", true);
	$.ajax({
		type: 'POST',
		url: '/ajax/qna_check_question',
		data: { pid: $("#pid").val(), 
			    que: $("#question").val(), 
			    cat: category, 
			    det: details, 
			    key: xsrf_key },
		success: function(response)
		{
			if(response.error)
			{
				alert(response.error);
				$(".qna_ask_next").prop("disabled", false);
			}
			else
				qna_ask_step(step);
		}

	});
}


function qna_post_question()
{
	if($('.flair_select .flair.current'))
		var category = $('.flair_select .flair.current').attr('data-id');
	else
		var category = 0;

	if($("#spoiler").prop('checked'))
		var spoiler = 1;
	else
		var spoiler = 0;

	if(!$("#pid").val() || !category || !$("#question").val() || !$("#details").val())
	{
		alert("There was an error processing your question; please go back and check to make sure everything looks right!");
		return;
	}

	$(".qna_ask_back, .qna_ask_next").prop("disabled", true);

	$.ajax({
		type: 'POST',
		url: '/ajax/qna_ask_question',
		data: { pid: $("#pid").val(), 
			    que: $("#question").val(), 
			    cat: category, 
			    det: $("#details").val(), 
			    spo: spoiler, 
			    ptt: $("#page_type_text").val(),
			    key: xsrf_key },
		success: function(response)
		{
			if(response.url)
			{
				window.location = response.url;
			}
			else if(response.error)
			{
				alert(response.error);
				$(".qna_ask_back, .qna_ask_next").prop("disabled", false);
			}
		}

	});
}

function log_out()
{
	$.ajax({
		type: 'GET',
		url: '/ajax/log_out',
		success: function(response)
		{
			window.location.reload();
		}
	});
}

function change_css(css)
{
	$('body').attr('data-css', css);
	if(css=='blue')
	{
		$.removeCookie('gf_css', { path: '/' });
		css = 'v13';
	}
	else
	{
		$.cookie('gf_css', css, { expires: 60, path: '/'});    
		css = 'v13-' + css;
	}
    $("link#core_css").attr("href", cdn_path + "/css/" + css + "." + css_date + ".css");

}



function mygames_add_to_list()
{
	$.ajax({
	type: 'POST',
    url: '/ajax/mygames_add_product_to_list',
    data: { list: $("#list_id").val(), product: $("#product_id").val(), title: $("#list_title").val(), notes: $("#user_notes").val(), key: xsrf_key },
    success: function(response)
	{
		$('#site_dialog').dialog('close');
		flyover_message(response.message);
		$('#gs_note').html(response.html);

    },
	error: function (xhr)
 	{
 		var message = JSON.parse(xhr.responseText);
 		alert(message.error);
	}

	});

}

function mygames_delete_from_list()
{

	$.ajax({
	type: 'POST',
    url: '/ajax/mygames_delete_product_from_list',
    data: { list: $("#list_id").val(), product: $("#product_id").val(), key: xsrf_key },
    success: function(response)
	{
		$('#site_dialog').dialog('close');
		flyover_message(response.message);
		$('#gs_note').html(response.html);
    },
	error: function (xhr)
 	{
 		var message = JSON.parse(xhr.responseText);
 		alert(message.error);
	}

	});

}


function mygames_show_add_dialog(game_id, product_id, list_id = 0)
{
	if($(document).width() < 500)
		var box_width = "98%";
	else
		var box_width = "30%";
	$.ajax({
		type: 'GET',
        url: '/ajax/mygames_add_dialog?game=' + game_id + '&product=' + product_id + '&list=' + list_id,
        success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({ resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){ $('.ui-widget-overlay').bind('click',function(){ $('#site_dialog').dialog('close');$('body').removeClass('modal_active');});$('body').addClass('modal_active');}, close: function(){ $('body').removeClass('modal_active');} });
        }

    });
    return false;
}

function password_validate(pass_check, name_check)
{
	if(pass_check.length < 8)
		return "Your password must be at least 8 characters long";
	if(pass_check.length > 64)
		return "Your password cannot be more than 64 characters long";
	if(!pass_check.match(/[a-z]/))
		return "Your password must include at least one lower-case letter";
	if(!pass_check.match(/[A-Z]/))
		return "Your password must include at least one upper-case letter";
	if(!pass_check.match(/[0-9]/))
		return "Your password must include at least one number";
	if(pass_check.match(/ /))
		return "Your password may not include spaces; dashes or underscores are fine";
	if(pass_check == name_check)
		return "Your password may not be identical to your username";
}

function username_validate(name_check)
{
	if(name_check.length < 3 || name_check.length > 15)
		return "User names must be between 3 and 15 characters long";
	if(name_check.match(/[^a-zA-Z0-9_-]/))
		return "User names may only include letters, numbers, dashes, and underscores";
}

function email_validate(mail_check)
{
	if(!mail_check.match(/^[a-zA-Z0-9.!#$%&’*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/))
		return "You must supply a valid email address";
	if(mail_check.match(/\.\.|\.@/))
		return "You must supply a valid email address";
	if(mail_check.match(/@(gnail|gmia|gmil|gmai|gamil|gmil|gail|gmsil)\.com/))
		return "You appear to have misspelled gmail.com";
}

function contrib_filter(c_class, platform)
{
	if(platform!=0)
	{
		$('ol.'+c_class+' li[data-platform="'+platform+'"]').show();
		$('ol.'+c_class+' li[data-platform!="'+platform+'"]').hide();
	}
	else
		$('ol.'+c_class+' li[data-platform]').show();
}

function show_verify(reload)
{
	if($(document).width() < 500)
		var box_width = "98%";
	else
		var box_width = "400px";
	$.ajax({
		type: 'GET',
        url: '/ajax/user_show_verify',
        data: { reload: reload },
        success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#site_dialog').dialog('close');$('body').removeClass('modal_active');});$('body').addClass('modal_active');}, close: function(){$('body').removeClass('modal_active');} });
        }
    });
    return false;
}

function show_change_email()
{
	if($(document).width() < 500)
		var box_width = "98%";
	else
		var box_width = "400px";
	$.ajax({
		type: 'GET',
        url: '/ajax/user_show_change_email',
        success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#site_dialog').dialog('close');$('body').removeClass('modal_active');});$('body').addClass('modal_active');}, close: function(){$('body').removeClass('modal_active');} });
        }
    });
    return false;
}

function show_reset_email(email = '')
{
	if($(document).width() < 500)
		var box_width = "98%";
	else
		var box_width = "400px";
	$.ajax({
		type: 'POST',
        url: '/ajax/user_show_reset_email',
        data: { email: email, key: xsrf_key },
        success: function(response)
		{
			$('#site_dialog').html(response);
			$('#site_dialog').dialog({	resizable: false, dialogClass: "reg_dialog", closeText: "X", height: "auto", width: box_width, modal: true, open: function(){$('.ui-widget-overlay').bind('click',function(){$('#site_dialog').dialog('close');$('body').removeClass('modal_active');});$('body').addClass('modal_active');}, close: function(){$('body').removeClass('modal_active');} });
        }
    });
    return false;
}

function update_user_game(game_id, action, option, product_id = 0)
{
	$.ajax({
	type: 'POST',
    url: '/ajax/update_user_game',
    data: { game_id: game_id, action: action, option: option, product_id: product_id, key: xsrf_key },
    success: function(response)
	{
		if(action=='add')
		{
			if($("#ug_" + option + " i").hasClass("fa-heart-o"))
			{
				$("#ug_" + option + " i").addClass("fa-heart").removeClass('fa-heart-o');
				$('#i_gs_fav').addClass("fa-heart").removeClass('fa-heart-o');
			}
			else
			{
				$("#ug_" + option + " i").addClass("fa-bell").removeClass('fa-bell-o');
				$('#i_gs_noty').addClass("fa-bell").removeClass('fa-bell-o');
			}
		}
		else
		{
			if($("#ug_" + option + " i").hasClass("fa-heart"))
			{
				$("#ug_" + option + " i").addClass("fa-heart-o").removeClass('fa-heart');
				if(response.favorite_game == 0 && response.favorite_board == 0)
					$('#i_gs_fav').addClass("fa-heart-o").removeClass('fa-heart');
			}
			else
			{
				$("#ug_" + option + " i").addClass("fa-bell-o").removeClass('fa-bell');
				if(!response.tracking.length > 0)
					$('#i_gs_noty').addClass("fa-bell-o").removeClass('fa-bell');
			}
		}
    },
	error: function (xhr)
 	{
 		var message = JSON.parse(xhr.responseText);
 		alert(message.error);
	}

	});
}

function dismiss_search_results()
{
	$('.game_selector, .gamespace_search').hide().empty();
}

$('#searchtextbox, #gs_search_input').val('');

$('#searchtextbox, #gs_search_input').click(function()
{
	$(this).focus();
});

function log_site_result(row, pt)
{
	if($('.game_selector div[data-row="'+row+'"]').length>0)
	{
		var pid = $('.game_selector div[data-row="'+row+'"]').attr('data-pid');
		var game_id = $('.game_selector div[data-row="'+row+'"]').attr('data-gameid');
		var query = $('#searchtextbox').val();
		var label = $('.game_selector div[data-row="'+row+'"] span.result_title a').first().text();
		$.ajax(
		{
			type: 'POST',
			url: '/ajax/log_search_click',
			data: { t:pt, s:query, c:label, r:row, x:1, p:pid, g:game_id, key:xsrf_key }
		});
	}
}