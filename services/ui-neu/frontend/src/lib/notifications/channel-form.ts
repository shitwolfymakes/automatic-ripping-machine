// The notification channel form's own fields in the field docs registry: the
// label, a script channel's script and timeout, and each subscribed event's
// overrides. A service's URL fields come from the service catalog instead.
export const FIELD_IDS = {
	label: 'form.notify_channel.label',
	script: 'form.notify_channel.script',
	timeout: 'form.notify_channel.timeout',
	event_title: 'form.notify_channel.event_title',
	event_body: 'form.notify_channel.event_body',
	event_input: 'form.notify_channel.event_input'
} as const;
