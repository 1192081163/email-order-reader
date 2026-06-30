import { Button, Field, Input, Title3 } from "@fluentui/react-components";

import type { AppSettings } from "../../shared/types";

type Props = {
  disabled: boolean;
  settings: AppSettings;
  onChange(settings: AppSettings): void;
  onSave(): void;
  onScanAll(): void;
};

export function SettingsPanel({ disabled, settings, onChange, onSave, onScanAll }: Props) {
  return (
    <section className="panel settings-panel" role="region" aria-label="邮件读取设置">
      <div className="panel-title">
        <Title3 as="h1">订单快读</Title3>
      </div>
      <div className="settings-fields">
        <Field label="邮箱账号">
          <Input
            autoComplete="username"
            disabled={disabled}
            value={settings.email}
            onChange={(_event, data) => onChange({ ...settings, email: data.value })}
          />
        </Field>
        <Field label="邮箱授权码">
          <Input
            autoComplete="current-password"
            disabled={disabled}
            type="password"
            value={settings.authCode}
            onChange={(_event, data) => onChange({ ...settings, authCode: data.value })}
          />
        </Field>
      </div>
      <div className="button-row">
        <Button disabled={disabled} onClick={onSave}>
          保存读取设置
        </Button>
        <Button appearance="primary" disabled={disabled} onClick={onScanAll}>
          读取近一周
        </Button>
      </div>
    </section>
  );
}
