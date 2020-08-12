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
            non_linearity=hparams["nonlin"]
        )

    def forward(self, node_features, adj, mask=None):
        mol_emb = self.graph_encoder(node_features, adj, mask)
        return mol_emb


class Decoder(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.fnn = FNN(
            input_dim=hparams["emb_dim"],
            hidden_dim=hparams["meta_node_decoder_hidden_dim"],
            output_dim=hparams["meta_node_decoder_hidden_dim"],
            num_layers=hparams["meta_node_decoder_num_layers"],
            non_linearity=hparams["nonlin"],
            batch_norm=hparams["batch_norm"],
        )
        self.edge_predictor = decoder.EdgePredictor(
            num_nodes=hparams["max_num_nodes"],
            input_dim=hparams["meta_node_decoder_hidden_dim"],
            hidden_dim=hparams["edge_predictor_hidden_dim"],
            num_layers=hparams["edge_predictor_num_layers"],
            batch_norm=hparams["batch_norm"],
            non_lin=hparams["nonlin"]
        )
        self.node_predictor = decoder.NodePredictor(
            num_nodes=hparams["max_num_nodes"],
            input_dim=hparams["meta_node_decoder_hidden_dim"],
            hidden_dim=hparams["node_decoder_hidden_dim"],
            num_layers=hparams["node_decoder_num_layers"],
            batch_norm=hparams["batch_norm"],
            num_node_features=hparams["num_atom_features"],
            non_lin=hparams["nonlin"]
        )

    def forward(self, z):
        x = self.fnn(z)
        edge_logits = self.edge_predictor(x)
        node_logits = self.node_predictor(x)
        return node_logits, edge_logits


class Descriminator(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.encoder = Encoder(hparams)
        self.linear = torch.nn.Linear(hparams["emb_dim"], hparams["emb_dim"])
        self.fnn = FNN(
            #input_dim=hparams["graph_encoder_num_layers"] * hparams["node_dim"],
            input_dim=hparams["emb_dim"],
            hidden_dim=512,
            output_dim=1,
            num_layers=4,
            non_linearity=hparams["nonlin"],
            batch_norm=False,
            dropout=0.2
        )

    def forward(self, node_features, adj, mask=None):
        emb = self.encoder(node_features, adj, mask)
        x = self.fnn(emb)
        return x, emb


class VAEEncoder(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.encoder = Encoder(hparams)
        self.linear_mu = torch.nn.Linear(hparams["emb_dim"], hparams["emb_dim"])
        self.linear_logvar = torch.nn.Linear(hparams["emb_dim"], hparams["emb_dim"])

    def forward(self, node_features, adj, mask=None):
        emb = self.encoder(node_features, adj, mask)
        mu = self.linear_mu(emb)
        logvar = self.linear_logvar(emb)
        z = reparameterize(mu, logvar)
        return z, mu, logvar


class VAEDecoder(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.generator = Decoder(hparams)

    def forward(self, z):
        nodes_fake_, adj_fake_ = self.generator(z)
        nodes_fake = postprocess(
            logits=nodes_fake_,
            method="hard_gumbel")
        adj_fake = postprocess(
            logits=adj_fake_,
            method="hard_gumbel")
        adj_fake = adj_fake[:, :, :, 1]
        return nodes_fake, adj_fake, nodes_fake_, adj_fake_


class GraphVAEGAN(torch.nn.Module):
    def __init__(self, hparams):
        super().__init__()
        self.hparams = hparams
        self.encoder = VAEEncoder(hparams)
        self.generator = VAEDecoder(hparams)
        self.discriminator = Descriminator(hparams)

    def forward(self, node_features, adj, mask=None):
        z, _, _ = self.encoder(node_features, adj, mask)
        node_features_, adj_, _, _ = self.generator(z)

        return node_features_, adj_, z


def reparameterize(mu, logvar):
    std = torch.exp(0.5 * logvar)
    eps = torch.randn_like(std)
    return mu + eps * std


def postprocess(logits, method, temperature=1.):
    shape = logits.shape
    if method == 'soft_gumbel':
        out = torch.nn.functional.gumbel_softmax(
            logits=logits.view(-1, shape[-1]) / temperature,
            hard=False
        )
    elif method == 'hard_gumbel':
        out = torch.nn.functional.gumbel_softmax(
            logits=logits.view(-1, shape[-1]) / temperature,
            hard=True
        )
    else:
        out = torch.nn.functional.softmax(
            input=logits / temperature
        )
    return out.view(shape)


