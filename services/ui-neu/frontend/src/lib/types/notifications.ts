// Hand-written types for the notification channel + catalog system.
// The BFF proxies channel data as opaque dicts, so these are not in the
// generated api.gen.ts. Catalog types mirror apprise-introspection output.

export type ChannelType = 'apprise' | 'webhook' | 'bash';

type AppriseFieldValue = string | number | boolean;

export interface AppriseConfig {
	type: 'apprise';
	url: string;
	service_id?: string | null;
	fields?: Record<string, AppriseFieldValue>;
}

interface WebhookConfig {
	type: 'webhook';
	url: string;
	shared_secret?: string | null;
	headers?: Record<string, string> | null;
}

interface BashConfig {
	type: 'bash';
	script: string;
	timeout_seconds?: number;
	inputs?: Record<string, string>;
	secret_keys?: string[];
}

type ChannelConfig = AppriseConfig | WebhookConfig | BashConfig;

export interface ChannelTemplate {
	title?: string | null;
	body?: string | null;
	inputs?: Record<string, string> | null;
}

export interface Channel {
	id: number;
	type: ChannelType;
	name: string;
	enabled: boolean;
	config: ChannelConfig;
	subscribed_events: string[];
	templates: Record<string, ChannelTemplate>;
	last_fired_at: string | null;
	last_success_at: string | null;
	last_error: string | null;
}

export interface ChannelCreate {
	type: ChannelType;
	name: string;
	enabled?: boolean;
	config: ChannelConfig;
	subscribed_events: string[];
	templates?: Record<string, ChannelTemplate>;
}

export interface ChannelUpdate {
	name?: string;
	enabled?: boolean;
	config?: ChannelConfig;
	subscribed_events?: string[];
	templates?: Record<string, ChannelTemplate>;
}

type FieldType = 'string' | 'bool' | 'choice' | 'int' | 'float';

export interface CatalogField {
	key: string;
	label: string;
	type: FieldType;
	private: boolean;
	required: boolean;
	default?: string | number | boolean | null;
	values?: string[];
}

export interface CatalogService {
	id: string;
	name: string;
	docs_url: string;
	url_scheme: string;
	required_fields: CatalogField[];
	advanced_fields: CatalogField[];
}

export interface Catalog {
	featured: string[];
	services: CatalogService[];
}

export interface DispatchRow {
	id: number;
	channel_id: number;
	event_key: string;
	status: 'pending' | 'in_flight' | 'success' | 'failed';
	attempts: number;
	last_error: string | null;
	created_at: string | null;
	completed_at: string | null;
}
