"""
modules/ml_engine/models/lstm_model.py
────────────────────────────────────────
LSTM-based time-series anomaly detection model (PyTorch).
Trains on sliding windows of metric sequences per service.
Uses reconstruction error as the anomaly signal.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


class LSTMAnomalyDetector(nn.Module):
    """
    LSTM autoencoder for time-series anomaly detection.
    Input:  (batch, seq_len, n_features)
    Output: (batch, seq_len, n_features)  — reconstructed sequence
    Anomaly score = mean squared reconstruction error.
    """

    def __init__(
        self,
        n_features: int,
        seq_len: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.seq_len = seq_len
        self.n_features = n_features
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # Encoder
        self.encoder = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        # Decoder
        self.decoder = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.output_layer = nn.Linear(hidden_size, n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Encode: compress sequence into context
        _, (hidden, cell) = self.encoder(x)
        # Use last hidden state repeated as decoder input
        decoder_input = hidden[-1].unsqueeze(1).repeat(1, self.seq_len, 1)
        # Decode: reconstruct sequence
        decoder_out, _ = self.decoder(decoder_input, (hidden, cell))
        reconstructed = self.output_layer(decoder_out)
        return reconstructed

    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        """Returns per-sample MSE reconstruction error (shape: [batch])."""
        reconstructed = self.forward(x)
        return torch.mean((x - reconstructed) ** 2, dim=(1, 2))


class LSTMTrainer:
    """Handles training and online update of the LSTM autoencoder."""

    def __init__(
        self,
        model: LSTMAnomalyDetector,
        learning_rate: float = 1e-3,
        device: str | None = None,
    ) -> None:
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model.to(self.device)
        self.optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
        self.loss_fn = nn.MSELoss()
        self._threshold: float = 0.05
        self._trained_on_samples: int = 0

    def fit(
        self,
        sequences: list[list[list[float]]],
        epochs: int = 50,
        batch_size: int = 64,
    ) -> dict[str, float]:
        """
        Full training from a list of sequences (each: [seq_len, n_features]).
        Returns training loss history summary.
        """
        x = torch.tensor(sequences, dtype=torch.float32)
        dataset = TensorDataset(x)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)

        self.model.train()
        epoch_losses = []
        for epoch in range(epochs):
            batch_losses = []
            for (batch,) in loader:
                batch = batch.to(self.device)
                self.optimizer.zero_grad()
                output = self.model(batch)
                loss = self.loss_fn(output, batch)
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                batch_losses.append(loss.item())
            epoch_loss = sum(batch_losses) / len(batch_losses)
            epoch_losses.append(epoch_loss)

        # Set threshold as 95th percentile of reconstruction errors on training data
        self.model.eval()
        with torch.no_grad():
            errors = self.model.reconstruction_error(x.to(self.device))
        self._threshold = float(torch.quantile(errors, 0.95).item())
        self._trained_on_samples = len(sequences)

        return {
            "final_loss": epoch_losses[-1],
            "initial_loss": epoch_losses[0],
            "threshold": self._threshold,
            "samples": self._trained_on_samples,
        }

    def score(self, sequence: list[list[float]]) -> float:
        """
        Score a single sequence. Returns normalized anomaly score [0, 1].
        0 = normal, 1 = highly anomalous (at or above threshold).
        """
        self.model.eval()
        x = torch.tensor([sequence], dtype=torch.float32).to(self.device)
        with torch.no_grad():
            error = self.model.reconstruction_error(x).item()
        # Clamp and normalize against threshold
        return min(error / max(self._threshold, 1e-6), 1.0)

    def online_update(
        self,
        sequence: list[list[float]],
        steps: int = 5,
    ) -> float:
        """
        Update model weights with a single new normal-data sample.
        Used for online learning when new normal patterns appear.
        Returns the current reconstruction error after update.
        """
        self.model.train()
        x = torch.tensor([sequence], dtype=torch.float32).to(self.device)
        final_loss = 0.0
        for _ in range(steps):
            self.optimizer.zero_grad()
            output = self.model(x)
            loss = self.loss_fn(output, x)
            loss.backward()
            self.optimizer.step()
            final_loss = loss.item()
        return final_loss

    def save(self, path: str) -> None:
        torch.save(
            {
                "model_state": self.model.state_dict(),
                "threshold": self._threshold,
                "trained_on_samples": self._trained_on_samples,
                "n_features": self.model.n_features,
                "seq_len": self.model.seq_len,
                "hidden_size": self.model.hidden_size,
                "num_layers": self.model.num_layers,
            },
            path,
        )

    @classmethod
    def load(cls, path: str, device: str | None = None) -> "LSTMTrainer":
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(path, map_location=device)
        model = LSTMAnomalyDetector(
            n_features=checkpoint["n_features"],
            seq_len=checkpoint["seq_len"],
            hidden_size=checkpoint["hidden_size"],
            num_layers=checkpoint["num_layers"],
        )
        model.load_state_dict(checkpoint["model_state"])
        trainer = cls(model, device=device)
        trainer._threshold = checkpoint["threshold"]
        trainer._trained_on_samples = checkpoint["trained_on_samples"]
        return trainer
