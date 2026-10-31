import type {
  VerificationReport,
  ConsistencyReport,
  ValidationResult,
} from "../lib/api";

export function VerificationPanel({
  verification,
  consistency,
  validation,
}: {
  verification?: VerificationReport | null;
  consistency?: ConsistencyReport | null;
  validation?: ValidationResult | null;
}) {
  if (!verification && !consistency && !validation) {
    return (
      <div className="draft-section verification-panel">
        <h3>Verification</h3>
        <p className="muted">No verification data available for this draft.</p>
      </div>
    );
  }

  const statusBadge = (status: string) => {
    const normalized = status.toLowerCase();
    if (normalized === "verified" || normalized === "passed" || normalized === "accepted") {
      return "status-badge ready";
    }
    if (normalized.includes("warning") || normalized === "warnings") {
      return "status-badge pending_review";
    }
    return "status-badge failed";
  };

  return (
    <div className="draft-section verification-panel">
      <h3>How this draft was verified</h3>

      {validation && (
        <div className="verification-row">
          <span className={statusBadge(validation.status)}>
            {validation.status.replaceAll("_", " ").toUpperCase()}
          </span>
          <span className="verification-label">Final validation gate</span>
          {validation.reason && <p className="verification-reason">{validation.reason}</p>}
        </div>
      )}

      {verification && (
        <div className="verification-block">
          <div className="verification-header">
            <span className={statusBadge(verification.status)}>
              {verification.status.replaceAll("_", " ").toUpperCase()}
            </span>
            <span className="verification-label">
              Citation check · threshold {(verification.threshold * 100).toFixed(0)}%
            </span>
          </div>
          <div className="verification-stats">
            <span>✅ {verification.supported_claims} supported</span>
            <span>⚠️ {verification.unsupported_claims} unsupported</span>
            {verification.low_confidence_claims > 0 && (
              <span>❓ {verification.low_confidence_claims} low confidence</span>
            )}
          </div>
          {verification.unsupported_details.length > 0 && (
            <ul className="verification-issues">
              {verification.unsupported_details.map((detail, idx) => (
                <li key={idx}>{detail}</li>
              ))}
            </ul>
          )}
          {verification.claims.length > 0 && (
            <details className="verification-details">
              <summary>Claim scores</summary>
              <ul className="verification-claims">
                {verification.claims.map((claim, idx) => (
                  <li key={idx} className={claim.supported ? "supported" : "unsupported"}>
                    <span>{claim.supported ? "✅" : "⚠️"}</span>
                    <span className="claim-text">{claim.claim}</span>
                    <span className="claim-score">{(claim.best_similarity * 100).toFixed(0)}%</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {consistency && (
        <div className="verification-block">
          <div className="verification-header">
            <span className={statusBadge(consistency.status)}>
              {consistency.status.replaceAll("_", " ").toUpperCase()}
            </span>
            <span className="verification-label">
              Consistency check · {consistency.rules_checked} rule
              {consistency.rules_checked === 1 ? "" : "s"} checked
            </span>
          </div>
          {consistency.injected_actions.length > 0 && (
            <div className="verification-injected">
              <strong>Auto-injected actions</strong>
              <ul>
                {consistency.injected_actions.map((action, idx) => (
                  <li key={idx}>{action}</li>
                ))}
              </ul>
            </div>
          )}
          {consistency.violations.length > 0 && (
            <ul className="verification-issues">
              {consistency.violations.map((v, idx) => (
                <li key={idx}>
                  Rule <b>{v.rule_key}</b>: expected {v.expected_action}
                </li>
              ))}
            </ul>
          )}
          {consistency.checks.length > 0 && (
            <details className="verification-details">
              <summary>Rule checks</summary>
              <ul className="verification-claims">
                {consistency.checks.map((check, idx) => (
                  <li key={idx} className={check.condition_fired ? "fired" : "passed"}>
                    <span>{check.condition_fired ? (check.action_present ? "✅" : "⚠️") : "✅"}</span>
                    <span className="claim-text">{check.message}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
