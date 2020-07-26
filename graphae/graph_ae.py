import torch
from graphae import encoder, decoder
from graphae.fully_connected import FNN


class Encoder(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.graph_encoder = encoder.GraphEncoder(
            input_dim=hparams["num_atom_features"],
            hidden_dim=hparams["graph_encoder_hidden_dim"],
            node_dim=hparams["node_dim"],
            emb_dim=hparams["emb_dim"],
            num_layers=hparams["graph_encoder_num_layers"],
            batch_norm=hparams["batch_norm"],
            non_linearity="lrelu"
        )

    def forward(self, node_features, adj, mask):
        mol_emb = self.graph_encoder(node_features, adj, mask)
        return mol_emb


class Decoder(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.meta_node_decoder = decoder.MetaNodeDecoder(
            num_nodes=hparams["max_num_nodes"],
            emb_dim=hparams["emb_dim"],
            meta_node_dim=hparams["meta_node_dim"],
            hidden_dim=hparams["meta_node_decoder_hidden_dim"],
            num_layers=hparams["meta_node_decoder_num_layers"],
            batch_norm=hparams["batch_norm"],
        )
        self.edge_predictor = decoder.EdgePredictor(
            num_nodes=hparams["max_num_nodes"],
            meta_node_dim=hparams["meta_node_dim"],
            hidden_dim=hparams["edge_predictor_hidden_dim"],
            num_layers=hparams["edge_predictor_num_layers"],
            batch_norm=hparams["batch_norm"],
        )
        self.node_predictor = decoder.NodePredictor(
            num_nodes=hparams["max_num_nodes"],
            meta_node_dim=hparams["meta_node_dim"],
            hidden_dim=hparams["node_decoder_hidden_dim"],
            num_layers=hparams["node_decoder_num_layers"],
            batch_norm=hparams["batch_norm"],
            num_node_features=hparams["num_atom_features"]
        )

    def forward(self, emb):
        meta_node_emb = self.meta_node_decoder(emb)
        adj = self.edge_predictor(meta_node_emb)
        node_features = self.node_predictor(meta_node_emb)
        mask, node_features = node_features[:, :, -1], node_features[:, :, :-1]
        return node_features, adj, mask


class SideTaskPredictor(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.fnn = FNN(
            input_dim=hparams["emb_dim"],
            hidden_dim=1024,
            output_dim=2,
            num_layers=4,
            non_linearity="elu",
            batch_norm=True,
        )

    def forward(self, emb):
        return self.fnn(emb)


class Descriminator(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.fnn = FNN(
            input_dim=hparams["emb_dim"],
            hidden_dim=1024,
            output_dim=1,
            num_layers=4,
            non_linearity="lrelu",
            batch_norm=False,
        )

    def forward(self, emb):
        out = self.fnn(emb)
        out = torch.sigmoid(out)
        return out


class GraphAE(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.encoder = Encoder(hparams)
        self.decoder = Decoder(hparams)

    def forward(self, node_features, adj, mask):
        mol_emb = self.encoder(node_features, adj, mask)
        node_features_, adj_, mask_ = self.decoder(mol_emb)

        return node_features_, adj_, mask_


def reparameterize(mu, logvar):
    std = torch.exp(0.5 * logvar)
    eps = torch.randn_like(std)
    return mu + eps * std


