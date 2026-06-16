type Props = {
  status: string;
  actionLabel?: string;
  disabled?: boolean;
  onAction?(): void;
};

export function StatusBar({ actionLabel, disabled = false, onAction, status }: Props) {
  return (
    <section className="panel status-bar">
      <span>{status}</span>
      {actionLabel && onAction ? (
        <button type="button" disabled={disabled} onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}
